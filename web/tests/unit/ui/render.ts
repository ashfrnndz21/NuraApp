import { Fragment, type VNode } from "preact";

/** A component's output as plain data, for tests with no DOM and no new dependency: function
 *  components are called with their props (the design system's components use no hooks, so
 *  this is exactly what Preact would render), fragments are flattened, text is kept. */

export interface El {
  type: string;
  props: Record<string, unknown>;
  children: Node[];
}
export type Node = El | string;

export function render(node: unknown): Node[] {
  if (node === null || node === undefined || typeof node === "boolean") return [];
  if (typeof node === "string" || typeof node === "number") return [String(node)];
  if (Array.isArray(node)) return node.flatMap(render);
  const vnode = node as VNode<Record<string, unknown>>;
  if (typeof vnode.type === "function") {
    if (vnode.type === Fragment) return render(vnode.props.children);
    return render((vnode.type as (props: unknown) => unknown)(vnode.props));
  }
  const { children, ...props } = vnode.props ?? {};
  return [{ type: String(vnode.type), props, children: render(children) }];
}

export function one(node: unknown): El {
  const [first] = render(node);
  if (!first || typeof first === "string") throw new Error("rendered no element");
  return first;
}

export function text(node: Node | Node[]): string {
  if (Array.isArray(node)) return node.map(text).join("");
  return typeof node === "string" ? node : text(node.children);
}

export function all(node: Node | Node[], match: (el: El) => boolean): El[] {
  const list = Array.isArray(node) ? node : [node];
  const found: El[] = [];
  for (const each of list) {
    if (typeof each === "string") continue;
    if (match(each)) found.push(each);
    found.push(...all(each.children, match));
  }
  return found;
}

export const hasClass = (name: string) => (el: El) => String(el.props.class ?? "").split(/\s+/).includes(name);
export const byTestId = (id: string) => (el: El) => el.props["data-testid"] === id;
export const byType = (type: string) => (el: El) => el.type === type;
