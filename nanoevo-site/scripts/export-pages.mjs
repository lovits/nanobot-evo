import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";

const basePath = "/nanobot-evo";
const productionOrigin = "https://lovits.github.io";
const outputRoot = new URL("../pages-dist/", import.meta.url);
const clientRoot = new URL("../dist/client/", import.meta.url);

await rm(outputRoot, { recursive: true, force: true });
await mkdir(outputRoot, { recursive: true });
await cp(clientRoot, outputRoot, { recursive: true });

function rewriteForPages(html) {
  return html
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
}

async function renderRoute(worker, pathname, expectedContent) {
  const response = await worker.fetch(
    new Request(`http://localhost${pathname}`, {
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
    throw new Error(`Static render for ${pathname} failed with status ${response.status}`);
  }

  const html = await response.text();
  if (!html.includes(expectedContent)) {
    throw new Error(`Static render for ${pathname} did not contain expected content`);
  }
  return rewriteForPages(html);
}

const workerUrl = new URL("../dist/server/index.js", import.meta.url);
workerUrl.searchParams.set("pages-export", Date.now().toString());
const { default: worker } = await import(workerUrl.href);
const homeHtml = await renderRoute(worker, "/", "让 Skills 从真实工作中学习");
const webuiHtml = await renderRoute(worker, "/webui", "Skill evolution management");

await mkdir(new URL("webui/", outputRoot), { recursive: true });
await writeFile(new URL("index.html", outputRoot), homeHtml, "utf8");
await writeFile(new URL("404.html", outputRoot), homeHtml, "utf8");
await writeFile(new URL("webui/index.html", outputRoot), webuiHtml, "utf8");
await writeFile(new URL(".nojekyll", outputRoot), "", "utf8");

const exported = await readFile(new URL("index.html", outputRoot), "utf8");
if (
  !exported.includes(`${basePath}/assets/`) ||
  !exported.includes(`${basePath}/evolution-diff.jpg`) ||
  exported.includes("/_vinext/image")
) {
  throw new Error("Static export contains invalid GitHub Pages asset paths");
}
