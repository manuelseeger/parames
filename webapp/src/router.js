import { ref } from 'vue';

function parse() {
  return window.location.hash.slice(1) || '/';
}

export const route = ref(parse());

window.addEventListener('hashchange', () => {
  route.value = parse();
});

export function navigate(path) {
  window.location.hash = path;
}

// Tiny matcher: returns null or a params object.
// Pattern uses ":id" for placeholders, e.g. "/alerts/:id".
export function match(pattern, path) {
  const pp = pattern.split('/');
  const ap = path.split('/');
  if (pp.length !== ap.length) return null;
  const params = {};
  for (let i = 0; i < pp.length; i++) {
    if (pp[i].startsWith(':')) params[pp[i].slice(1)] = ap[i];
    else if (pp[i] !== ap[i]) return null;
  }
  return params;
}
