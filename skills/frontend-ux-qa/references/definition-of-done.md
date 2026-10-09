# Definition of Done (UI) —— 粘贴到 AGENTS.md / DESIGN.md

## Blocking (MUST, CI)

- [ ] No h-overflow at 320/360/390/480/600/768/834/1024/1180/1280/1440/1920. [L]
- [ ] Reflow 320-equiv single column, no 2D scroll. [L-07]
- [ ] axe 0 violations all routes/states. [A]
- [ ] Text >=4.5:1 (large >=3:1); UI borders/icons >=3:1. [A-01]
- [ ] Label for all controls; placeholder != label. [A-03,F-01]
- [ ] Name for all link/button; icon-only aria-label. [A-04,A-05]
- [ ] `<html lang>` correct. [A-06]
- [ ] `:focus-visible` present, never obscured. [A-08,L-10]
- [ ] No div/span onClick as control. [A-09]
- [ ] img/video/iframe sized; no global img{width:auto}. [V-01,V-02]
- [ ] Lighthouse A11y>=95; CLS<=0.1; LCP<=2.5s; INP<=200ms (throttled cold). [V]
- [ ] Tokens only, no hardcoded color/space/size/radius/duration. [D-02,G-09]

## Blocking (NEVER)

- [ ] NEVER outline:none w/o :focus-visible. [A-08]
- [ ] NEVER user-scalable=no/maximum-scale=1. [L-13]
- [ ] NEVER fixed width on layout containers. [L-01]
- [ ] NEVER nowrap on UGC. [L-03]
- [ ] NEVER overflow:hidden on text/interactive. [L-09]
- [ ] NEVER disabled-button as validation. [F-05]
- [ ] NEVER block paste. [F-10]
- [ ] NEVER hover-only. [I-01]
- [ ] NEVER animate w/h/top/left/margin. [V-05]
- [ ] NEVER nested modals/alert/confirm/prompt. [N-07]
- [ ] NEVER gradient text/emoji headings/full glass. [D-06,D-13]

## States & fixtures

- [ ] loading/empty/error/forbidden/offline/partial/success-stale; empty has next action; error has retry; refresh keeps data. [S]
- [ ] Minimal/Typical/Maximal/Pathological per component. [C]

## Manual

- [ ] Automated key journeys pass before visual review when applicable; visual-trigger decision is recorded. For layout/interaction/state changes, Agent opened and reviewed screenshots for changed UI states, including action result, close/cancel/focus return, overlap/compression, clipping and responsive controls. Pure copy-only changes may record justified `N/A`. [G-10]
- [ ] Keyboard-only + focus return; 200%/400% + spacing + 400px height. [A-10,L-12]
- [ ] Win+Mac; iOS 16px/safe-area/dvh. [P]
- [ ] IME composing Enter not submit. [F-16]
- [ ] Dark: no pure b/w, elevation readable, no FOUC. [D-15..D-19]

来源：`references/catalog.md` 验收方法论一节；阈值依据见该节末表。
