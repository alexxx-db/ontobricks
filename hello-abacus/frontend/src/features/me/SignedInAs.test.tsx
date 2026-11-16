import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import SignedInAs from "./SignedInAs";

function respond(body: unknown) {
  const fetch = vi.fn().mockResolvedValueOnce({ ok: body !== null, json: async () => body });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("shows who is signed in", async () => {
  respond({ email: "ada@example.com" });

  render(<SignedInAs />);

  expect(await screen.findByText("Signed in as ada@example.com")).toBeTruthy();
});

test("shows nothing when the user cannot be loaded", async () => {
  const fetch = respond(null);

  const { container } = render(<SignedInAs />);

  await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/me"));
  expect(container.textContent).toBe("");
});
