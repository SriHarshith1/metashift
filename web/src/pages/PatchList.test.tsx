import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";
import indexFixture from "../test/fixtures/index.json";
import type { IndexFile } from "../types/generated";
import PatchList from "./PatchList";

vi.mock("../data", () => ({ fetchIndex: vi.fn() }));
import { fetchIndex } from "../data";

function renderList(path = "/lol") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/:game" element={<PatchList />} />
      </Routes>
    </MemoryRouter>,
  );
}

test("PatchList renders rows newest first with counts", async () => {
  vi.mocked(fetchIndex).mockResolvedValue(indexFixture as IndexFile);
  renderList();
  const rows = await screen.findAllByRole("listitem");
  expect(rows).toHaveLength(3);
  expect(rows[0]).toHaveTextContent("26.21");
  expect(rows[0]).toHaveTextContent("9 buffs");
  expect(rows[0]).toHaveTextContent("ollama:qwen3:14b");
  expect(rows[1]).toHaveTextContent("26.20");
  expect(rows[2]).toHaveTextContent("26.19");
  expect(within(rows[0]).getByRole("link")).toHaveAttribute("href", "/lol/26.21");
});

test("PatchList shows the error text when the index fails to load", async () => {
  vi.mocked(fetchIndex).mockRejectedValue(new Error("could not load data/index.json"));
  renderList();
  expect(await screen.findByText("could not load data/index.json")).toBeInTheDocument();
});

test("PatchList says when a game has no patches", async () => {
  vi.mocked(fetchIndex).mockResolvedValue(indexFixture as IndexFile);
  renderList("/dota");
  expect(await screen.findByText(/no patches published for dota/i)).toBeInTheDocument();
});
