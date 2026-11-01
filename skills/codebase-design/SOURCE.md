## 来源与本地取舍

- 上游：[Matt Pocock skills](https://github.com/mattpocock/skills)。
- 依据：提交 `4ae2317ddb22b046e26455e4f9c9b3aaaf62212d` 的 `skills/engineering/codebase-design/`。
- 许可：MIT，版权归 Matt Pocock，见 [LICENSE](LICENSE)。
- 本地版本为中文改编，独立维护，不是上游原样安装，也不自动跟随 main。

保留深模块、删除检验、接口知识负担、局部性与测试边界的设计方法。沿用项目命名，不强制禁用 service/API 等术语；候选比较不默认派多个代理；删除旧测试需先核覆盖，替身不替代真实集成。职责分给 domain-modeling、swe-gov、web-app-testing、code-review 与 ai-verified-delivery，不另建工程治理或验收流程。

更新时对比上游方法变化与本地边界，按需采纳；保留本地触发、授权和证据政策。许可证随适配版分发。
