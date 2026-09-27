from __future__ import annotations

import asyncio
from collections import deque
from pathlib import Path
from typing import Any

import pytest
import site_session as subject


class FakeResponse:
    def __init__(self, url: str, html: str, status: int = 200) -> None:
        self.url = url
        self.html_content = html
        self.status = status


class FakePage:
    async def content(self) -> str:
        return "<html><title>Normal</title><body>normal</body></html>"


class FakeSession:
    def __init__(self, responses: dict[str, list[FakeResponse]], delay: float = 0.0) -> None:
        self.responses = {url: deque(values) for url, values in responses.items()}
        self.delay = delay
        self.calls: list[str] = []
        self.call_kwargs: list[dict[str, Any]] = []
        self.active = 0
        self.max_active = 0
        self.closed = False

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *args: Any) -> None:
        self.closed = True

    async def fetch(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append(url)
        self.call_kwargs.append(kwargs)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            page_setup = kwargs.get("page_setup")
            if page_setup:
                await page_setup(FakePage())
            if self.delay:
                await asyncio.sleep(self.delay)
            queue = self.responses[url]
            if len(queue) > 1:
                return queue.popleft()
            return queue[0]
        finally:
            self.active -= 1


class FakeFactory:
    def __init__(self, session: FakeSession) -> None:
        self.session = session
        self.kwargs: dict[str, Any] = {}

    def __call__(self, **kwargs: Any) -> FakeSession:
        self.kwargs = kwargs
        return self.session


def normal_response(url: str, text: str) -> FakeResponse:
    return FakeResponse(url, f"<html><title>{text}</title><body>{text}</body></html>")


def options(home_url: str = "https://example.com/") -> subject.SiteSessionOptions:
    return subject.SiteSessionOptions(
        home_url=home_url,
        min_bytes=1,
        expected_home_texts=("Home",),
        timeout_ms=60_000,
        wall_timeout_ms=60_000,
        challenge_poll_ms=100,
        post_wait_ms=0,
    )


@pytest.mark.asyncio
async def test_warmup_is_singleflight_and_reuses_one_session() -> None:
    home = "https://example.com/"
    session = FakeSession({home: [normal_response(home, "Home")]}, delay=0.02)
    factory = FakeFactory(session)
    manager = subject.SiteSessionManager(options(), session_factory=factory)

    async with manager:
        first, second = await asyncio.gather(manager.warmup(), manager.warmup())

    assert first.html == second.html
    assert session.calls == [home]
    assert session.closed
    assert factory.kwargs["headless"] is False
    assert factory.kwargs["max_pages"] == 3


@pytest.mark.asyncio
async def test_fetch_many_warms_once_and_limits_page_concurrency() -> None:
    home = "https://example.com/"
    urls = [f"https://example.com/product/{number}" for number in range(4)]
    responses = {home: [normal_response(home, "Home")]}
    responses.update({url: [normal_response(url, f"Product {url}")] for url in urls})
    session = FakeSession(responses, delay=0.02)
    configured = options()
    configured = subject.SiteSessionOptions(
        **{**configured.__dict__, "max_pages": 2, "concurrency": 2}
    )

    async with subject.SiteSessionManager(configured, session_factory=FakeFactory(session)) as site:
        results = await site.fetch_many(urls)

    assert [result.url for result in results] == urls
    assert session.calls.count(home) == 1
    assert session.max_active == 2
    assert session.call_kwargs[0]["solve_cloudflare"] is True
    assert all(kwargs["solve_cloudflare"] is False for kwargs in session.call_kwargs[1:])


@pytest.mark.asyncio
async def test_challenge_response_pauses_rewarms_and_retries_page() -> None:
    home = "https://example.com/"
    product = "https://example.com/product"
    challenge = FakeResponse(
        product,
        "<html><title>Just a moment...</title><script src='/cdn-cgi/challenge-platform/x' "
        "data-cf-chl-test='1'></script></html>",
        status=403,
    )
    session = FakeSession(
        {
            home: [normal_response(home, "Home"), normal_response(home, "Home")],
            product: [challenge, normal_response(product, "Product")],
        }
    )

    async with subject.SiteSessionManager(options(), session_factory=FakeFactory(session)) as site:
        result = await site.fetch(subject.SiteRequest(product, expected_texts=("Product",)))

    assert result.status == 200
    assert session.calls == [home, product, home, product]
    assert [kwargs["solve_cloudflare"] for kwargs in session.call_kwargs] == [
        True,
        False,
        True,
        True,
    ]


@pytest.mark.asyncio
async def test_missing_business_text_raises_structured_error() -> None:
    home = "https://example.com/"
    product = "https://example.com/product"
    session = FakeSession(
        {
            home: [normal_response(home, "Home")],
            product: [normal_response(product, "Other")],
        }
    )

    with pytest.raises(subject.PageRejectedError) as captured:
        async with subject.SiteSessionManager(
            options(), session_factory=FakeFactory(session)
        ) as site:
            await site.fetch(subject.SiteRequest(product, expected_texts=("Expected",)))

    assert captured.value.request.url == product
    assert captured.value.reasons == ("missing_expected_text:Expected",)


@pytest.mark.asyncio
async def test_expected_business_text_is_case_insensitive_by_default() -> None:
    home = "https://example.com/"
    product = "https://example.com/product"
    session = FakeSession(
        {
            home: [normal_response(home, "Home")],
            product: [normal_response(product, "OPTICLIMATE 6000 PRO3")],
        }
    )

    async with subject.SiteSessionManager(options(), session_factory=FakeFactory(session)) as site:
        result = await site.fetch(
            subject.SiteRequest(product, expected_texts=("OptiClimate 6000 PRO3",))
        )

    assert result.status == 200


@pytest.mark.asyncio
async def test_expected_selector_is_verified_in_returned_html() -> None:
    home = "https://example.com/"
    product = "https://example.com/product"
    session = FakeSession(
        {
            home: [normal_response(home, "Home")],
            product: [normal_response(product, "No heading")],
        }
    )

    with pytest.raises(subject.PageRejectedError) as captured:
        async with subject.SiteSessionManager(
            options(), session_factory=FakeFactory(session)
        ) as site:
            await site.fetch(subject.SiteRequest(product, expected_selector="h1.product_title"))

    assert captured.value.reasons == ("missing_expected_selector:h1.product_title",)


@pytest.mark.asyncio
async def test_same_origin_redirect_is_allowed_by_default() -> None:
    home = "https://example.com/"
    product = "https://example.com/product"
    redirected = normal_response("https://example.com/login", "Login")
    session = FakeSession({home: [normal_response(home, "Home")], product: [redirected]})

    async with subject.SiteSessionManager(options(), session_factory=FakeFactory(session)) as site:
        result = await site.fetch(product)

    assert result.final_url == "https://example.com/login"


@pytest.mark.asyncio
async def test_strict_path_check_rejects_redirect() -> None:
    home = "https://example.com/"
    product = "https://example.com/product"
    redirected = normal_response("https://example.com/login", "Login")
    session = FakeSession({home: [normal_response(home, "Home")], product: [redirected]})

    with pytest.raises(subject.PageRejectedError) as captured:
        async with subject.SiteSessionManager(
            options(), session_factory=FakeFactory(session)
        ) as site:
            await site.fetch(subject.SiteRequest(product, require_same_path=True))

    assert captured.value.reasons == ("final_path_mismatch:https://example.com/login",)


@pytest.mark.asyncio
async def test_default_profile_is_fresh_and_removed_after_close() -> None:
    home = "https://example.com/"
    session = FakeSession({home: [normal_response(home, "Home")]})
    factory = FakeFactory(session)
    manager = subject.SiteSessionManager(options(), session_factory=factory)

    async with manager as site:
        profile = site.profile_dir
        assert site.profile_is_temporary
        assert profile is not None and profile.is_dir()
        assert factory.kwargs["user_data_dir"] == str(profile)

    assert profile is not None and not profile.exists()
    assert manager.profile_dir is None


@pytest.mark.asyncio
async def test_explicit_profile_is_preserved_after_close(tmp_path: Path) -> None:
    home = "https://example.com/"
    profile = tmp_path / "persistent-profile"
    configured = subject.SiteSessionOptions(**{**options().__dict__, "profile_dir": profile})
    session = FakeSession({home: [normal_response(home, "Home")]})

    async with subject.SiteSessionManager(configured, session_factory=FakeFactory(session)) as site:
        assert not site.profile_is_temporary
        assert site.profile_dir == profile.resolve()

    assert profile.is_dir()


@pytest.mark.asyncio
async def test_cross_origin_request_is_rejected_before_navigation() -> None:
    home = "https://example.com/"
    session = FakeSession({home: [normal_response(home, "Home")]})

    async with subject.SiteSessionManager(options(), session_factory=FakeFactory(session)) as site:
        with pytest.raises(ValueError, match="同源"):
            await site.fetch("https://other.example/page")

    assert session.calls == []


@pytest.mark.asyncio
async def test_challenge_callback_fires_once() -> None:
    challenge_html = (
        "<html><title>Just a moment...</title>"
        "<script src='/cdn-cgi/challenge-platform/x' data-cf-chl-test='1'></script></html>"
    )
    contents = deque([challenge_html, challenge_html, "<html><title>Home</title></html>"])
    events: list[subject.ChallengeEvent] = []

    class ChangingPage:
        async def content(self) -> str:
            return contents.popleft() if len(contents) > 1 else contents[0]

    manager = subject.SiteSessionManager(options(), on_challenge=events.append)
    await manager._monitor_challenge(ChangingPage(), "https://example.com/")

    assert len(events) == 1
    assert events[0].headless is False
    assert manager.state is subject.SiteSessionState.CHALLENGE


@pytest.mark.parametrize(
    "overrides",
    [
        {"concurrency": 4},
        {"timeout_ms": 59_999},
        {"wall_timeout_ms": 59_999},
        {"challenge_poll_ms": 99},
    ],
)
def test_options_reject_invalid_lifecycle_limits(overrides: dict[str, Any]) -> None:
    values: dict[str, Any] = {
        "home_url": "https://example.com/",
        "timeout_ms": 60_000,
        "wall_timeout_ms": 60_000,
    }
    values.update(overrides)
    with pytest.raises(ValueError):
        subject.SiteSessionOptions(**values)
