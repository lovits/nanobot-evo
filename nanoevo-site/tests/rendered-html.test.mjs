import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

const projectRoot = new URL("../", import.meta.url);

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("https://nanoevo.example/", {
      headers: {
        accept: "text/html",
        host: "nanoevo.example",
        "x-forwarded-host": "nanoevo.example",
        "x-forwarded-proto": "https",
      },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("server-renders the NanoEvo showcase", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>NanoEvo — 可审计的 Skill 演化控制层<\/title>/i);
  assert.match(html, /让 Skills 从真实工作中学习/);
  assert.match(html, /Human approval by default/);
  assert.match(html, /77\.8%/);
  assert.match(html, /https:\/\/nanoevo\.example\/og\.png/);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape|react-loading-skeleton/i);
});

test("ships the required public visual assets", async () => {
  await Promise.all([
    access(new URL("public/og.png", projectRoot)),
    access(new URL("public/evolution-diff.jpg", projectRoot)),
    access(new URL("public/nanoevo-icon.png", projectRoot)),
  ]);
});

test("exports a self-contained GitHub Pages entrypoint", async () => {
  const html = await readFile(new URL("pages-dist/index.html", projectRoot), "utf8");

  assert.match(html, /让 Skills 从真实工作中学习/);
  assert.match(html, /\/nanobot-evo\/assets\//);
  assert.match(html, /\/nanobot-evo\/evolution-diff\.jpg/);
  assert.match(html, /https:\/\/lovits\.github\.io\/nanobot-evo\/og\.png/);
  assert.doesNotMatch(html, /\/_vinext\/image|<script\b|\/nanobot-evo\/nanobot-evo\//i);
  assert.doesNotMatch(html, /(?<!\/nanobot-evo)\/assets\/_vinext_fonts/);
});
