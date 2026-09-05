export function proxyRequestHeaders(headers) {
  const forwarded = {};

  if (headers['content-type']) {
    forwarded['Content-Type'] = headers['content-type'];
  }

  if (headers['content-length']) {
    forwarded['Content-Length'] = headers['content-length'];
  }

  return forwarded;
}
