import type { Layout } from "./hooks";
import type { ThemePref } from "./theme";

/** 展示壳（父页面） → 设计稿（iframe） */
export type ToFrame =
  | { type: "nimbus:theme"; value: ThemePref }
  | { type: "nimbus:navigate"; to: string }
  | { type: "nimbus:sidebar"; action: "pin-expanded" | "pin-collapsed" | "peek-on" | "peek-off" };

/** 设计稿（iframe） → 展示壳 */
export interface FrameState {
  type: "nimbus:state";
  path: string;
  layout: Layout;
  pinned: "expanded" | "collapsed";
  expanded: boolean;
  peek: boolean;
  drawer: boolean;
  width: number;
  variant: string;
}
export type FromFrame = FrameState | { type: "nimbus:ready" };

export function postToParent(msg: FromFrame) {
  if (window.parent !== window) window.parent.postMessage(msg, "*");
}

export function postToFrame(win: Window | null | undefined, msg: ToFrame) {
  win?.postMessage(msg, "*");
}
