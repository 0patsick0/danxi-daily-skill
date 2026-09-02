const DISPATCH_URL =
  "https://api.github.com/repos/0patsick0/danxi-daily-skill/actions/workflows/daily-post.yml/dispatches";

async function dispatch(env, { dryRun = false } = {}) {
  const token = env.GITHUB_DISPATCH_TOKEN;
  if (!token) {
    throw new Error("GITHUB_DISPATCH_TOKEN is not set");
  }

  const payload = { ref: "main" };
  if (dryRun) {
    payload.inputs = { dry_run: "true" };
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
    body: JSON.stringify(payload),
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
  async fetch(request, env) {
    const auth = request.headers.get("Authorization") || "";
    const expected = env.CLOCK_KEY || env.GITHUB_DISPATCH_TOKEN;
    if (!expected || auth !== `Bearer ${expected}`) {
      return new Response("forbidden\n", { status: 403 });
    }
    const dryRun = new URL(request.url).searchParams.get("dry_run") === "true";
    try {
      await dispatch(env, { dryRun });
      return new Response(dryRun ? "dispatched dry_run\n" : "dispatched\n", { status: 200 });
    } catch (error) {
      return new Response(String(error), { status: 500 });
    }
  },
};
