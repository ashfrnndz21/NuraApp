import { describe, expect, it } from "vitest";
import { DemoSignIn } from "../../src/screens/Welcome";
import { all, byTestId, render } from "./ui/render";

/** "Try it as Pa"/"Try it as Mei" (docs/deploy-demo.md): the Welcome screen's two demo/dev
 *  shortcuts show only when the deployment says it is a demo or a dev run (`GET /deployment`,
 *  `demo`/`dev` in `src/store/deployment.ts`) — never on an ordinary deployment. */
describe("the Welcome screen's demo/dev sign-in shortcuts", () => {
  it("show both buttons when the deployment is a demo or a dev run", () => {
    for (const show of [true]) {
      const tree = render(
        <DemoSignIn show={show} onTry={() => {}} busy={null} error={null} />,
      );
      expect(all(tree, byTestId("welcome-demo-signin"))).toHaveLength(1);
      expect(all(tree, byTestId("welcome-try-pa"))).toHaveLength(1);
      expect(all(tree, byTestId("welcome-try-mei"))).toHaveLength(1);
    }
  });

  it("render nothing on an ordinary deployment", () => {
    const tree = render(<DemoSignIn show={false} onTry={() => {}} busy={null} error={null} />);
    expect(tree).toEqual([]);
    expect(all(tree, byTestId("welcome-try-pa"))).toHaveLength(0);
    expect(all(tree, byTestId("welcome-try-mei"))).toHaveLength(0);
  });

  it("disables both buttons while one of them is signing in", () => {
    const tree = render(<DemoSignIn show={true} onTry={() => {}} busy="pa" error={null} />);
    const [pa] = all(tree, byTestId("welcome-try-pa"));
    const [mei] = all(tree, byTestId("welcome-try-mei"));
    expect(pa.props.disabled).toBe(true);
    expect(mei.props.disabled).toBe(true);
  });
});
