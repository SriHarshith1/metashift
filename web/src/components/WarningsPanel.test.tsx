import { render, screen } from "@testing-library/react";
import WarningsPanel from "./WarningsPanel";

test("WarningsPanel renders nothing for no warnings", () => {
  const { container } = render(<WarningsPanel warnings={[]} />);
  expect(container).toBeEmptyDOMElement();
});

test("WarningsPanel is a collapsed details with the count", () => {
  const { container } = render(<WarningsPanel warnings={["No stats found.", "Old tier list."]} />);
  const details = container.querySelector("details")!;
  expect(details).not.toHaveAttribute("open");
  expect(screen.getByText(/warnings \(2\)/i)).toBeInTheDocument();
  expect(screen.getByText("No stats found.")).toBeInTheDocument();
});
