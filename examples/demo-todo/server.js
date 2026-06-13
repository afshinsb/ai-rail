const http = require("http");

let todos = [
  { id: 1, title: "Try AI Rail", done: false },
  { id: 2, title: "Close three issues", done: false }
];

function json(res, status, body) {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(body, null, 2));
}

const server = http.createServer((req, res) => {
  if (req.method === "GET" && req.url === "/todos") {
    return json(res, 200, todos);
  }

  if (req.method === "POST" && req.url === "/todos") {
    // Issue #1: add body validation.
    todos.push({ id: Date.now(), title: "Untitled", done: false });
    return json(res, 201, todos[todos.length - 1]);
  }

  if (req.method === "DELETE" && req.url.startsWith("/todos/")) {
    // Issue #2: return 404 when missing.
    const id = Number(req.url.split("/").pop());
    todos = todos.filter((todo) => todo.id !== id);
    return json(res, 200, { ok: true });
  }

  return json(res, 404, { error: "not found" });
});

server.listen(3000, () => {
  console.log("Demo TODO running on http://localhost:3000");
});
