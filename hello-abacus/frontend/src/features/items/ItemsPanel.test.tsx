import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import ItemsPanel from "./ItemsPanel";

function respond(...bodies: unknown[]) {
  const fetch = vi.fn();
  for (const body of bodies) {
    fetch.mockResolvedValueOnce({ ok: body !== null, json: async () => body });
  }
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("lists items on load", async () => {
  respond([{ id: 1, name: "first" }]);

  render(<ItemsPanel />);

  expect(await screen.findByText("first")).toBeTruthy();
});

test("adds an item and reloads the list", async () => {
  const fetch = respond([], { id: 2, name: "second" }, [{ id: 2, name: "second" }]);
  render(<ItemsPanel />);

  fireEvent.change(screen.getByLabelText("Item name"), { target: { value: "second" } });
  fireEvent.click(screen.getByText("Add"));

  expect(await screen.findByText("second")).toBeTruthy();
  expect(fetch).toHaveBeenNthCalledWith(2, "/api/items", expect.objectContaining({ method: "POST", body: '{"name":"second"}' }));
});

test("shows an error when saving fails", async () => {
  respond([], null);
  render(<ItemsPanel />);

  fireEvent.change(screen.getByLabelText("Item name"), { target: { value: "x" } });
  fireEvent.click(screen.getByText("Add"));

  expect((await screen.findByRole("alert")).textContent).toBe("Could not save item");
});
