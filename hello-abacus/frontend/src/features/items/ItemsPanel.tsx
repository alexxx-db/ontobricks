import { type FormEvent, useEffect, useState } from "react";

import { createItem, type Item, listItems } from "./api";

export default function ItemsPanel() {
  const [items, setItems] = useState<Item[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState("");

  async function loadItems() {
    setItems(await listItems());
  }

  useEffect(() => {
    loadItems().catch((err: Error) => setError(err.message));
  }, []);

  async function addItem(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    try {
      await createItem(name);
    } catch (err) {
      setError((err as Error).message);
      return;
    }
    setName("");
    await loadItems();
  }

  return (
    <>
      <form onSubmit={addItem}>
        <input
          aria-label="Item name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Add an item"
          required
        />
        <button type="submit">Add</button>
      </form>
      {error && <p role="alert">{error}</p>}
      <ul>
        {items.map((item) => (
          <li key={item.id}>{item.name}</li>
        ))}
      </ul>
    </>
  );
}
