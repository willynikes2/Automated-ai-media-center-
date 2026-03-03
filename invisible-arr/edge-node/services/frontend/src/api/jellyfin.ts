import { jellyfinApi } from './client';

export async function initiateQuickConnect(): Promise<{ Secret: string; Code: string }> {
  const res = await jellyfinApi.post('/QuickConnect/Initiate');
  return res.data;
}

export async function checkQuickConnect(secret: string): Promise<{ Authenticated: boolean }> {
  const res = await jellyfinApi.get('/QuickConnect/Connect', { params: { Secret: secret } });
  return res.data;
}

export async function authorizeQuickConnect(code: string): Promise<void> {
  await jellyfinApi.post('/QuickConnect/Authorize', null, { params: { Code: code } });
}

export async function getServerInfo() {
  const res = await jellyfinApi.get('/System/Info');
  return res.data;
}

export async function triggerLibraryScan() {
  await jellyfinApi.post('/Library/Refresh');
}
