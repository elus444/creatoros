export function sessionFromMe(me, fallbackToken) {
  const nextToken =
    typeof me?.access_token === "string" && me.access_token ? me.access_token : fallbackToken;
  return {
    token: nextToken,
    user: {
      id: me.id,
      email: me.email,
      full_name: me.full_name,
      created_at: me.created_at,
    },
  };
}
