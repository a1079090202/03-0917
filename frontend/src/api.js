async function req(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    let msg = `请求失败（${res.status}）`
    try {
      const j = await res.json()
      if (typeof j.detail === 'string') msg = j.detail
      else if (Array.isArray(j.detail)) msg = j.detail.map(e => e.msg).join('；')
    } catch { /* 保留默认提示 */ }
    throw new Error(msg)
  }
  return res.json()
}

export const api = {
  get: (url) => req('GET', url),
  post: (url, body) => req('POST', url, body),
}
