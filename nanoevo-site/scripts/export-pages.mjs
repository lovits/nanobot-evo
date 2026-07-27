import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";

const basePath = "/nanobot-evo";
const productionOrigin = "https://lovits.github.io";
const outputRoot = new URL("../pages-dist/", import.meta.url);
const clientRoot = new URL("../dist/client/", import.meta.url);

await rm(outputRoot, { recursive: true, force: true });
await mkdir(outputRoot, { recursive: true });
await cp(clientRoot, outputRoot, { recursive: true });

const workerUrl = new URL("../dist/server/index.js", import.meta.url);
workerUrl.searchParams.set("pages-export", Date.now().toString());
const { default: worker } = await import(workerUrl.href);
const response = await worker.fetch(
  new Request("http://localhost/", {
    headers: {
      accept: "text/html",
      host: "localhost",
      "x-forwarded-host": "lovits.github.io",
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

if (!response.ok) {
  throw new Error(`Static render failed with status ${response.status}`);
}

let html = await response.text();
if (!html.includes("让 Skills 从真实工作中学习")) {
  throw new Error("Static render did not contain the NanoEvo hero content");
}

html = html
  .replace(
    /\/_vinext\/image\?url=%2Fevolution-diff\.jpg(?:&amp;|&)w=\d+(?:&amp;|&)q=\d+/g,
    `${basePath}/evolution-diff.jpg`,
  )
  .replace(
    new RegExp(`${productionOrigin.replaceAll(".", "\\.")}/og\\.png`, "g"),
    `${productionOrigin}${basePath}/og.png`,
  )
  .replace(
    /(href|src)="\/(?!\/|nanobot-evo(?:\/|"))([^"]*)"/g,
    (_, attribute, path) => `${attribute}="${basePath}/${path}"`,
  )
  .replace(
    /(?<!\/nanobot-evo)\/assets\/_vinext_fonts/g,
    `${basePath}/assets/_vinext_fonts`,
  )
  .replace(/<link rel="modulepreload"[^>]*\/>/g, "")
  .replace(/<script[^>]*>[\s\S]*?<\/script>/g, "");

await writeFile(new URL("index.html", outputRoot), html, "utf8");
await writeFile(new URL("404.html", outputRoot), html, "utf8");
await writeFile(new URL(".nojekyll", outputRoot), "", "utf8");

const exported = await readFile(new URL("index.html", outputRoot), "utf8");
if (
  !exported.includes(`${basePath}/assets/`) ||
  !exported.includes(`${basePath}/evolution-diff.jpg`) ||
  exported.includes("/_vinext/image")
) {
  throw new Error("Static export contains invalid GitHub Pages asset paths");
}
