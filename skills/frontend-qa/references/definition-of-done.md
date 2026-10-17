# Definition of Done (UI) —— 粘贴到 AGENTS.md / DESIGN.md

本文件是本 skill 的 **UI 完成清单唯一模板**；catalog 引用本文件，不维护副本。下列条目按实际变更、产品支持范围与 [唯一等级矩阵](../../ai-verified-delivery/references/levels-and-gates.md)选取，所需检查缺工具仍记未执行，不能写成不适用。总体完成结论使用交付政策；截图触发、采集与证据使用 [视觉验收](../../ai-verified-delivery/references/visual-acceptance.md)。需在项目中保存快照时注明来源与版本。

## Blocking (MUST, CI)

- [ ] No unintended h-overflow at supported widths, affected breakpoint boundaries and regression widths; record the selected matrix. [L]
- [ ] Reflow 320-equiv single column, no 2D scroll. [L-07]
- [ ] axe checks pass on applicable routes/states; record scope and resolve relevant incomplete/manual items. [A]
- [ ] Text incl. placeholder/read-only >=4.5:1 (large >=3:1); required UI cues/icons >=3:1 against adjacent colors. Product enhancements separately marked. [A-01]
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
- [ ] Animation properties, performance and reduced-motion results follow [the animation guide](../../web-animation-guide/references/performance-a11y.md); do not replace its policy with a blanket property ban. [V-05]
- [ ] NEVER nested modals/alert/confirm/prompt. [N-07]
- [ ] Visual treatment follows confirmed design requirements; aesthetic preferences alone do not block acceptance. [D-06,D-13]

## States & fixtures

- [ ] loading/empty/error/forbidden/offline/partial/success-stale; empty has next action; error has retry; refresh keeps data. [S]
- [ ] Minimal/Typical/Maximal/Pathological per component. [C]

## Manual

- [ ] Changed color pairs measured on actual composed backgrounds across supported themes/states; complex backgrounds and axe incomplete items resolved; readability checked and evidence recorded. [A-01]
- [ ] Applicable user-flow automation and Agent screenshot review follow the shared [visual acceptance protocol](../../ai-verified-delivery/references/visual-acceptance.md); UI observations include action result, close/cancel/focus return, overlap/compression, clipping and responsive controls. [G-10]
- [ ] Keyboard-only + focus return; 200%/400% + spacing + 400px height. [A-10,L-12]
- [ ] Supported OS/browser checks selected by impact; iOS input sizing/safe-area/viewport checks when iOS is supported. [P]
- [ ] IME composing Enter not submit. [F-16]
- [ ] Dark: no pure b/w, elevation readable, no FOUC. [D-15..D-19]

UI 条目的分类与诊断依据见 [catalog.md](catalog.md) 的对应类别，阈值来源见该文件的来源声明与验收方法论；catalog 只引用本模板。色对、例外与测量方法见 [对比度与可读性](../../frontend-design/references/contrast-readability.md)。
