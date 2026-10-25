import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";
import indexFixture from "../test/fixtures/index.json";
import type { IndexFile } from "../types/generated";
import Layout, { DISCLAIMER } from "./Layout";

vi.mock("../data", () => ({ fetchIndex: vi.fn() }));
import { fetchIndex } from "../data";

function renderLayout() {
  vi.mocked(fetchIndex).mockResolvedValue(indexFixture as IndexFile);
  return render(
    <MemoryRouter initialEntries={["/lol"]}>
      <Routes>
        <Route element={<Layout />}>
          <Route path=":game" element={<p>content</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});

test("footer shows the exact Riot disclaimer", () => {
  renderLayout();
  expect(screen.getByRole("contentinfo")).toHaveTextContent(
    "Metashift isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. Riot Games, and all associated properties are trademarks or registered trademarks of Riot Games, Inc.",
  );
  expect(DISCLAIMER.startsWith("Metashift isn't endorsed")).toBe(true);
});

test("game switcher lists the games in the index", async () => {
  renderLayout();
  expect(await screen.findByRole("option", { name: "lol" })).toBeInTheDocument();
});

test("theme toggle sets data-theme and saves the choice", async () => {
  const user = userEvent.setup();
  renderLayout();
  await user.click(screen.getByRole("button", { name: /switch to dark theme/i }));
  expect(document.documentElement.dataset.theme).toBe("dark");
  expect(localStorage.getItem("metashift-theme")).toBe("dark");
  expect(screen.getByRole("button", { name: /switch to light theme/i })).toBeInTheDocument();
});
