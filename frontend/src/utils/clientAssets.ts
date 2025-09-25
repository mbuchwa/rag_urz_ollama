type ClientAssets = {
  background: string | null
  logo: string | null
  chatbotLogo: string | null
}

const DEFAULT_CLIENT_SLUG = 'urz'

const assetModules = import.meta.glob('../../imgs/*/*.{png,jpg,jpeg,JPG,JPEG}', {
  eager: true,
  import: 'default',
}) as Record<string, string>

const CLIENT_ASSET_MAP: Record<string, Partial<ClientAssets>> = {}

for (const [fullPath, url] of Object.entries(assetModules)) {
  const segments = fullPath.split('/')
  const fileName = segments.pop() ?? ''
  const clientSlug = segments.pop() ?? ''
  if (!clientSlug || !fileName) continue

  const extensionIndex = fileName.lastIndexOf('.')
  if (extensionIndex === -1) continue

  const baseName = fileName.slice(0, extensionIndex).toLowerCase()
  let key: keyof ClientAssets | null = null
  if (baseName === 'background') key = 'background'
  else if (baseName === 'logo') key = 'logo'
  else if (baseName === 'chatbot_logo') key = 'chatbotLogo'

  if (!key) continue

  const normalizedSlug = clientSlug.toLowerCase()
  const target = (CLIENT_ASSET_MAP[normalizedSlug] ||= {})
  target[key] = url
}

const DEFAULT_ASSETS: ClientAssets = {
  background: CLIENT_ASSET_MAP[DEFAULT_CLIENT_SLUG]?.background ?? null,
  logo: CLIENT_ASSET_MAP[DEFAULT_CLIENT_SLUG]?.logo ?? null,
  chatbotLogo: CLIENT_ASSET_MAP[DEFAULT_CLIENT_SLUG]?.chatbotLogo ?? null,
}

function mergeAssets(preferred: Partial<ClientAssets> | undefined): ClientAssets {
  return {
    background: preferred?.background ?? DEFAULT_ASSETS.background ?? null,
    logo: preferred?.logo ?? DEFAULT_ASSETS.logo ?? null,
    chatbotLogo: preferred?.chatbotLogo ?? DEFAULT_ASSETS.chatbotLogo ?? null,
  }
}

export function getClientAssets(slug?: string | null): ClientAssets {
  const normalized = slug?.toLowerCase()
  if (!normalized) {
    return mergeAssets(undefined)
  }
  return mergeAssets(CLIENT_ASSET_MAP[normalized])
}

export type { ClientAssets }
