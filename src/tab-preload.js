const { contextBridge } = require('electron');

const WINDOWS_PLATFORM = 'Win32';
const WINDOWS_USER_AGENT =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36';
const USER_AGENT_DATA_BRANDS = [
  { brand: 'Chromium', version: '142' },
  { brand: 'Google Chrome', version: '142' },
  { brand: 'Not=A?Brand', version: '24' }
];
const FIGMA_AUTH_PATH_PREFIXES = ['/login', '/signup', '/oauth'];

function installFigmaNavigatorSpoof() {
  contextBridge.executeInMainWorld({
    func: (windowsUserAgent, windowsPlatform, brands, authPathPrefixes) => {
      const hostname = (window.location.hostname || '').toLowerCase();
      const pathname = window.location.pathname || '/';
      const isFigmaHost = hostname === 'figma.com' || hostname.endsWith('.figma.com');
      const isAuthPath = authPathPrefixes.some((prefix) => pathname.startsWith(prefix));

      if (!isFigmaHost || isAuthPath) {
        return;
      }

      const defineGetter = (object, key, getter) => {
        if (!object) {
          return;
        }

        try {
          Object.defineProperty(object, key, {
            configurable: true,
            enumerable: true,
            get: getter
          });
        } catch {
          // Ignore non-configurable properties.
        }
      };

      const navigatorPrototype = window.Navigator && window.Navigator.prototype;
      const appVersion = windowsUserAgent.replace(/^Mozilla\//, '');
      const baseUserAgentData =
        navigator.userAgentData && typeof navigator.userAgentData === 'object'
          ? navigator.userAgentData
          : null;
      const spoofedUserAgentData = {
        brands,
        mobile: false,
        platform: 'Windows',
        getHighEntropyValues: async (hints) => {
          const values = {};
          const requestedHints = Array.isArray(hints) ? hints : [];

          for (const hint of requestedHints) {
            switch (hint) {
              case 'architecture':
                values.architecture = 'x86';
                break;
              case 'bitness':
                values.bitness = '64';
                break;
              case 'brands':
                values.brands = brands;
                break;
              case 'fullVersionList':
                values.fullVersionList = brands.map((brand) => ({
                  brand: brand.brand,
                  version: `${brand.version}.0.0.0`
                }));
                break;
              case 'mobile':
                values.mobile = false;
                break;
              case 'model':
                values.model = '';
                break;
              case 'platform':
                values.platform = 'Windows';
                break;
              case 'platformVersion':
                values.platformVersion = '19.0.0';
                break;
              case 'uaFullVersion':
                values.uaFullVersion = '142.0.0.0';
                break;
              case 'wow64':
                values.wow64 = false;
                break;
              default:
                break;
            }
          }

          return values;
        },
        toJSON: () => ({
          brands,
          mobile: false,
          platform: 'Windows'
        })
      };

      defineGetter(navigatorPrototype, 'platform', () => windowsPlatform);
      defineGetter(navigatorPrototype, 'userAgent', () => windowsUserAgent);
      defineGetter(navigatorPrototype, 'appVersion', () => appVersion);
      defineGetter(navigatorPrototype, 'userAgentData', () => spoofedUserAgentData);

      if (baseUserAgentData && typeof baseUserAgentData.getHighEntropyValues === 'function') {
        try {
          baseUserAgentData.getHighEntropyValues = spoofedUserAgentData.getHighEntropyValues;
        } catch {
          // Ignore immutable objects.
        }
      }
    },
    args: [
      WINDOWS_USER_AGENT,
      WINDOWS_PLATFORM,
      USER_AGENT_DATA_BRANDS,
      FIGMA_AUTH_PATH_PREFIXES
    ]
  });
}

installFigmaNavigatorSpoof();
