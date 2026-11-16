import { useEffect, useState } from "react";

import { getMe } from "./api";

export default function SignedInAs() {
  const [email, setEmail] = useState("");

  useEffect(() => {
    // Without a user the app's data calls fail with their own errors, so this line just stays empty.
    getMe()
      .then((me) => setEmail(me.email))
      .catch(() => undefined);
  }, []);

  if (!email) return null;
  return <p className="intro">Signed in as {email}</p>;
}
