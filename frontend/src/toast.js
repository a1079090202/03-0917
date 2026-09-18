// 极简全局 toast：任何页面 import 后 toast.ok('...') / toast.err(e.message)
let host = null

export const toast = {
  bind(fn) { host = fn },
  show(type, msg) { host && host(type, msg) },
  ok(msg) { this.show('ok', msg) },
  err(msg) { this.show('err', typeof msg === 'string' ? msg : (msg?.message || '操作失败')) },
  info(msg) { this.show('info', msg) },
}
