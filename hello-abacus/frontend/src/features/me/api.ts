export type Me = { email: string };

export async function getMe(): Promise<Me> {
  const response = await fetch("/api/me");
  if (!response.ok) throw new Error("Could not load the signed-in user");
  return response.json();
}
