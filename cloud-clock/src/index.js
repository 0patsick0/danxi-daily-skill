const DISPATCH_URL =
  "https://api.github.com/repos/0patsick0/danxi-daily-skill/actions/workflows/daily-post.yml/dispatches";

async function dispatch(env) {
  const token = env.GITHUB_DISPATCH_TOKEN;
  if (!token) {
    throw new Error("GITHUB_DISPATCH_TOKEN is not set");
  }

  const response = await fetch(DISPATCH_URL, {
    method: "POST",
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "danxi-daily-cloud-clock",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ref: "main" }),
  });

  if (response.status !== 204) {
    const body = await response.text();
    throw new Error(`GitHub dispatch failed ${response.status}: ${body.slice(0, 500)}`);
  }
}

export default {
  async scheduled(_event, env, _ctx) {
    await dispatch(env);
  },
  async fetch(_request, env) {
    try {
      await dispatch(env);
      return new Response("dispatched\n", { status: 200 });
    } catch (error) {
      return new Response(String(error), { status: 500 });
    }
  },
};
