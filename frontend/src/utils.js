export const BATCH_STATUS = {
  NORMAL: { text: '正常', cls: 'b-ok' },
  QC_SUSPENDED: { text: '质检停售', cls: 'b-warn' },
  EXPIRED_LOCKED: { text: '过期锁死', cls: 'b-bad' },
}

export const LEDGER_TYPE = {
  INBOUND: '入库',
  SALE: '销售出库',
  SPLIT_SALE: '拆零出库',
  TRANSFER_OUT: '调拨出',
  TRANSFER_IN: '调拨入',
  EXPIRY_LOCK: '过期锁死',
  QC_SUSPEND: '质检停售',
  QC_RELEASE: '质检放行',
}

export const TRANSFER_STATUS = {
  IN_TRANSIT: { text: '在途', cls: 'b-warn' },
  RECEIVED: { text: '已收货', cls: 'b-ok' },
  CANCELLED: { text: '已取消', cls: 'b-muted' },
}

export const ORDER_TYPE = { SALE: '销售', SPLIT_SALE: '拆零' }

export function lastMonth() {
  const d = new Date()
  d.setDate(1)
  d.setMonth(d.getMonth() - 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}
