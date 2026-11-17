export type Item = { id: number; name: string };

export async function listItems(): Promise<Item[]> {
  const response = await fetch("/api/items");
  if (!response.ok) throw new Error("Could not load items");
  return response.json();
}

export async function createItem(name: string): Promise<Item> {
  const response = await fetch("/api/items", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!response.ok) throw new Error("Could not save item");
  return response.json();
}
