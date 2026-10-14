// Service worker: right-click "Ask AEGIS", toolbar icon opens the side panel, alert badge every 5 minutes.
import { MAX_QUESTION, countAlerts } from './shared.js'

const MENU_ID = 'aegis-ask'
const ALARM = 'aegis-alerts'

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({ id: MENU_ID, title: 'Ask AEGIS: what if "%s"?', contexts: ['selection'] })
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {})
  chrome.alarms.create(ALARM, { periodInMinutes: 5, delayInMinutes: 0.1 })
})
chrome.runtime.onStartup.addListener(() => chrome.alarms.create(ALARM, { periodInMinutes: 5, delayInMinutes: 0.1 }))

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== MENU_ID || !info.selectionText) return
  // open first (must happen inside the user gesture), then hand the question to the panel
  const opening = chrome.sidePanel.open({ windowId: tab.windowId }).catch(() => {})
  const question = info.selectionText.trim().slice(0, MAX_QUESTION)
  await chrome.storage.session.set({ pendingQuestion: { text: question, source: tab?.title || '', at: Date.now() } })
  await opening
})

async function refreshBadge() {
  try {
    const { n, ok } = await countAlerts()
    await chrome.action.setBadgeBackgroundColor({ color: n ? '#c42b2b' : '#15803d' })
    await chrome.action.setBadgeText({ text: !ok ? '!' : n ? String(n) : '' })
    await chrome.action.setTitle({ title: !ok ? 'AEGIS: backend not reachable' : n ? `AEGIS: ${n} alert(s) need attention` : 'AEGIS: no urgent alerts' })
  } catch {
    await chrome.action.setBadgeText({ text: '!' })
  }
}
chrome.alarms.onAlarm.addListener((a) => a.name === ALARM && refreshBadge())
chrome.runtime.onMessage.addListener((msg) => {
  if (msg?.type === 'refresh-badge') refreshBadge()
})
