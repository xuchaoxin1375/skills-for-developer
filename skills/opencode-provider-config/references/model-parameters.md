# 第三方模型参数配置（OpenCode V2）

适用于新建模型，以及给已有模型补模态、工具、思考档位和窗口。配置形状先核对官方 V2 [Models](https://opencode.ai/v2/docs/models/) 与 [Providers](https://opencode.ai/v2/docs/providers/)；不要因旧教程或兼容 schema 接受某字段就沿用 V1 写法。本文只说明参数落地，不要求重接供应商、更换密钥或运行真实模型请求。

## 先核实什么

- **模型身份与渠道**：记录实际请求 ID、上游模型版本、套餐/路由；展示名和同系列名称不能证明能力相同。网关别名不明时先问清，不能靠模型自己回答身份来取证。
- **能力证据**：优先查上游官方模型卡，网关说明用于核对明确的渠道差异；思考档位按下文的公开档位配置基线处理。OpenRouter、models.dev、LiteLLM 只作参数线索，不用其他模型或渠道的条目代替目标模型规格。
- **控制范围**：是否会推理、是否能关闭、是否能选努力等级、是否能设 token 预算是不同问题。`supported_parameters` 含 `reasoning` 或布尔 `reasoning=true` 只证明有限信息，不给出合法等级集合。
- **缺失与冲突**：区分 `false`、空列表与未提供。证据冲突时先查模型版本和渠道限制；未决项标未知，保留已有可靠配置，不用一次文本应答推断所有能力。

## 证据映射到哪里

下列均在 `providers.<providerID>.models.<modelID>` 内；请求相关字段另见后文。

| 已核实的信息 | V2 配置位置 | 易错点 |
| --- | --- | --- |
| 网关侧请求 ID | `modelID` | 仅与配置 map 的键不同时才写；引用仍用 map 的键。 |
| 输入、输出模态 | `capabilities.input`、`capabilities.output` | 两者为数组。只列该路由接受的类型，不能把支持图片输入写成图片输出；音频、视频、PDF 等须确认 V2 及所选 package 的支持，不凭模型宣传添加。 |
| 工具调用 | `capabilities.tools` | 布尔值；会文本对话不等于可做 agent。明确不支持时写 `false`，不能靠省略让自定义模型的默认假设替代事实。 |
| 推理及其控制 | `capabilities.reasoning` | 对象，含 `supported` 及适用的 `effort`、`toggle`、`budget`；不是 V1 的顶层布尔 `reasoning`。 |
| 总上下文、独立输入上限、输出上限 | `limit.context`、`limit.input`、`limit.output` | token 数而非字符数；只写有依据的项。`max_input_tokens` 不能未经核对就当总窗口，不能把输入/输出上限相加来猜窗口。 |
| 该渠道的价格 | `cost` | 按 V2 格式及每百万 token 单位配置；区分输入、输出与缓存费用。套餐、路由与长上下文价可能不同，不照搬聚合平台价格，也不因未知填零。 |
| 是否支持温度采样 | `capabilities` 的温度支持声明 | 能力声明不等于采样值；具体字段形状和 `settings` 参数先核对当前 V2/package 文档。不支持或未知时不强加 temperature/topP。 |
| 类型、显示及分组信息 | `type`、`name`、`family`、`releaseDate` | 仅按需补；非 chat 模型不作为会话 agent。 |

**新建条目要警惕回退假设**：V2 官方文档说明，未进入 catalog 的模型默认假设支持工具、文本/图片输入、文本输出，并给出通用窗口与输出值。这不是能力检测。已知纯文本或无工具支持的模型应显式纠正；未知项必须在交付中说明，不能称为“完整配置”。

`limit` 是 OpenCode 的预算声明，不会扩展网关能力。总窗口、独立输入限制、为回答和思考预留的输出空间共同约束可用输入；不能把 `limit.context` 当作全部可供用户粘贴的文本长度。思考 token 是否占输出预算以具体 API 为准。仅改窗口不必顺带改压缩策略，也不要通过超长付费请求默认探测极限。

## 思考档位与默认行为

### 公开档位配置基线

模型身份和所用协议明确时，默认按该模型上游官方公开的完整思考档位配置，不因第三方网关缺少单独声明而删档、保留通用三档或阻断配置。只有渠道明确限制、可复现的参数拒绝或已确认的协议映射不支持时才缩减，并说明依据；尚未实测只影响验证状态，不影响公开档位的配置。

以下仅示范声明结构，假定示例模型公开支持这三个等级；实际配置应替换为目标模型的完整合法集合，不把示例当作通用档位：

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "providers": {
    "<providerID>": {
      "models": {
        "<modelID>": {
          "capabilities": {
            "tools": true,
            "input": ["text", "image"],
            "output": ["text"],
            "reasoning": {
              "supported": true,
              "effort": ["low", "medium", "high"]
            }
          },
          "limit": { "context": 200000, "output": 32000 }
        }
      }
    }
  }
}
```

V2 根据 `capabilities.reasoning` 与所选 `package` 生成 variants：

- `supported: false` 或仅 `supported: true` 而没有控制项，都不生成推理 variants；后者表示会推理但尚未声明可调控件。
- `effort` 填目标模型官方公开的完整合法集合，按上述基线处理已知限制。`low/medium/high` 不是跨模型标准；`minimal/none/xhigh/max` 等不能因为别的模型支持就添加。`default` 保留供应商默认，不生成同名 variant。
- `toggle: true` 会增加关闭推理的 `none` variant；目标模型公开支持关闭且所用协议可映射时声明，不能把最低努力档当作关闭。
- `budget` 可含 `min`、`max` 思考 token 范围；仅预算式控制时采用。存在 `effort` 时 V2 忽略 `budget`，不要同时写两套并声称均生效。

模型原生支持努力等级，不代表当前兼容协议的 package 能正确映射。生成结果应从服务目录核对；不足时按下面的方法配置经文档确认的请求选项，不盲目拼协议字段。

### 需要自定义档名或显式默认值时

`variants` 在 V2 是**数组**，每项有 `id` 和可选的 `settings`、`headers`、`body`，不是 V1 的名称到选项的 map。显式 variants 会叠加在能力自动生成的 variants 上，同 ID 替换；不要假定加一个自定义档位会清空原有档位。

以下只适用于所选 package 通过 `reasoningEffort` 映射思考等级的模型，渠道差异按公开档位配置基线处理；`fast/deep` 是自定义显示档名，不是供应商 API 参数：

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "providers": {
    "<providerID>": {
      "models": {
        "<modelID>": {
          "settings": { "reasoningEffort": "medium" },
          "variants": [
            { "id": "fast", "settings": { "reasoningEffort": "low" } },
            { "id": "deep", "settings": { "reasoningEffort": "high" } }
          ]
        }
      }
    }
  }
}
```

- 模型级 `settings` 决定未选 variant 时的请求选项；未要求默认档位时保留供应商默认，不自行设最高档来增加时延和费用。
- 会话、单次 run、agent 或 command 可选择 `<providerID>/<modelID>#deep`；这里只说明引用语法，不代表获准执行 `opencode run`。
- 顶层 `model` 当前不会保留默认 variant，不能靠在那里写 `#high` 固定全局努力等级；需要模型级默认请求选项时用经确认的 `settings`。
- 思考预算、努力等级与 `reasoningSummary` 是不同控制。能选择高努力不等于 API 会返回完整思考文本，也不应为了显示思考而默认强加摘要参数。

## 能力、请求选项与协议兼容不要混写

- `capabilities` 声明模型可做什么；`settings` 是 package 接受的选项；`body` 是需原样并入请求的额外 JSON 字段；`compatibility` 处理该协议的请求/响应差异。
- 请求选项按 provider → model → variant 叠加；嵌套 `settings/body` 合并，后来的数组与标量替换，header 名不区分大小写。模型族混用的网关优先放模型级，避免把一种模型的思考参数施加给全部模型。
- `settings.reasoningEffort` 不能直接改写成 `body.reasoning_effort` 或 Responses 的嵌套结构；Chat、Responses、Messages 的线上字段不相同。以所选 package 和路由的当前文档为准，不同时在 settings 与 body 写同一控制的冲突值。
- 仅当网关有文档化的私有控制、package 未提供映射时考虑 `body`，并标明适用路由；不把未知字段藏进 body 来绕过校验。
- 需要读写自定义推理流字段时，按 V2 [Compatibility](https://opencode.ai/v2/docs/models/#compatibility) 核对 `compatibility.reasoningField`、`requireReasoning`；需要调整输出参数名时核对 `maxTokensField`。这些 OpenAI Chat 兼容项不是思考等级，也不能照搬到 Messages 或 Responses。
- 缓存格式、价格和是否支持工具分别核实。声明缓存能力或填写缓存价格不会自动让第三方网关支持 prompt caching。

## 验收与交付

1. **局部修改**：先读既有配置，只改用户目标字段。只调 `limit.context` 不重写其余 limit、能力或 variants；补模态时列清输入/输出，不顺带替换已工作的协议。
2. **目录校验**：配置保存自动热加载，必要时 `/reload`；不为普通配置变更重启服务。从相同项目位置运行 `opencode api get /api/model`，按目标 ID 过滤后核对能力、limit、package、生成/显式 variants 与请求选项。输出结构可能是解析/归一化后的形状，按语义核对，不要求与配置逐字相同。
3. **按授权验证**：目录出现档位只证明 OpenCode 识别，不证明网关接受或真的执行了该档。用户明确授权后才做最小真实请求或本地模拟请求检查；验思考选项要看请求映射与网关反馈，验图片要用有明确答案的小图，验工具要覆盖调用及工具结果回传。不逐个穷举全部档位，不为参数补全默认跑付费 harness 或抓包。
4. **说明结论**：交付目标模型与变更字段、依据和未决项；分别写“文档已核实”“服务目录已识别”“真实调用已验证/未执行”。文本 `OK` 不能证明图片、工具、各思考等级或最大窗口都已验证。

桌面走查时至少考虑：公开完整档位而渠道未声明时仍完整配置，并标明未实测；渠道明确限制或可复现地拒绝某档时才按依据缩减；纯文本模型不能继承为图片输入；只知“支持推理”不能凭空列等级；只支持 budget 时不能抄 effort；网关低于上游窗口时不能按上游更大值配置；已有模型只改一个字段时不能丢掉其他选项。
