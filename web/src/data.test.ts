import { vi } from "vitest";
import { fetchIndex, fetchReport } from "./data";

afterEach(() => vi.unstubAllGlobals());

test("fetchReport requests the game/patch file under BASE_URL", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ patch: "26.21" }) });
  vi.stubGlobal("fetch", fetchMock);
  const report = await fetchReport("lol", "26.21");
  expect(report.patch).toBe("26.21");
  expect(fetchMock).toHaveBeenCalledWith(`${import.meta.env.BASE_URL}data/lol/26.21.json`);
});

test("a failed fetch throws could not load with the path", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));
  await expect(fetchIndex()).rejects.toThrow("could not load data/index.json");
});

test("a network error throws could not load with the path", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
  await expect(fetchReport("lol", "26.99")).rejects.toThrow("could not load data/lol/26.99.json");
});
