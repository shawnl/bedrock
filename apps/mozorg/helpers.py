"""
Download buttons. Let's get some terminology straight. Here is a list
of terms and example values for them:

* product: 'firefox' or 'thunderbird'
* version: 7.0, 8.0b3, 9.0a2
* build: 'beta', 'aurora', or None (for latest)
* platform: 'os_windows', 'os_linux', or 'os_osx'
* locale: a string in the form of 'en-US'
"""

from os import path
import re
import urlparse

import jinja2
import jingo
from django import shortcuts
from django.conf import settings
from funfactory.urlresolvers import reverse
from product_details import product_details


download_urls = {
    'transition': '/products/download.html',
    'direct': 'http://download.mozilla.org/',
    'aurora': 'http://ftp.mozilla.org/pub/mozilla.org/firefox/nightly/latest-mozilla-aurora',
    'aurora-l10n': 'http://ftp.mozilla.org/pub/mozilla.org/firefox/nightly/latest-mozilla-aurora-l10n'
}


def latest_aurora_version(locale):
    builds = product_details.firefox_primary_builds
    vers = product_details.firefox_versions['FIREFOX_AURORA']

    if locale in builds and vers in builds[locale]:
        return vers, builds[locale]


def latest_beta_version(locale):
    builds = product_details.firefox_primary_builds
    vers = product_details.firefox_versions['LATEST_FIREFOX_DEVEL_VERSION']

    if locale in builds and vers in builds[locale]:
        return vers, builds[locale]


def latest_version(locale):
    beta_vers = product_details.firefox_versions['FIREFOX_AURORA']
    aurora_vers = product_details.firefox_versions['LATEST_FIREFOX_DEVEL_VERSION']
    esr_vers = product_details.firefox_versions['FIREFOX_ESR']

    def _check_builds(builds):
        if locale in builds and isinstance(builds[locale], dict):
            # The json should be already ordered in increasing
            # order. The previous PHP code assumed this, so it should
            # work.
            for version, info in reversed(builds[locale].items()):
                match = (version != beta_vers and
                         version != aurora_vers and
                         version != esr_vers and
                         info)
                if match:
                    return version, info

    return (_check_builds(product_details.firefox_primary_builds) or
            _check_builds(product_details.firefox_beta_builds))


def make_aurora_link(product, version, platform, locale):
    # Download links are different for localized versions
    src = 'aurora' if locale.lower() == 'en-us' else 'aurora-l10n'

    filename = {
        'os_windows': 'win32.installer.exe',
        'os_linux': 'linux-i686.tar.bz2',
        'os_osx': 'mac.dmg'
    }[platform]

    return ('%s/%s-%s.%s.%s' %
            (download_urls[src], product, version, locale, filename))


def make_download_link(product, build, version, platform, locale,
                       force_direct=False):
    # Aurora has a special download link format
    if build == 'aurora':
        return make_aurora_link(product, version, platform, locale)

    # The downloaders expect the platform in a certain format
    platform = {
        'os_windows': 'win',
        'os_linux': 'linux',
        'os_osx': 'osx'
    }[platform]

    # Figure out the base url. certain locales have a transitional
    # thankyou-style page (most do)
    src = 'direct'
    if locale in settings.LOCALES_WITH_TRANSITION and not force_direct:
         src = 'transition'

    return ('%s?product=%s-%s&os=%s&lang=%s' %
            (download_urls[src], product, version, platform, locale))


@jingo.register.function
@jinja2.contextfunction
def download_button(ctx, id, format='large', build=None):
    locale = ctx['request'].locale

    def latest(locale):
        if build == 'aurora':
            return latest_aurora_version(locale)
        elif build == 'beta':
            return latest_beta_version(locale)
        else:
            return latest_version(locale)

    version, platforms = latest(locale) or latest('en-US')

    # Gather data about the build for each platform
    builds = []
    for platform in ['Windows', 'Linux', 'OS X']:
        # Fallback to en-US if this platform/version isn't available
        # for the current locale
        _locale = locale
        if platform not in platforms:
            _locale = 'en-US'

        # Normalize the platform name
        platform = 'os_%s' % platform.lower().replace(' ', '')
        platform_pretty = {
            'os_osx': 'Mac OS X',
            'os_windows': 'Windows',
            'os_linux': 'Linux'
        }[platform]

        # And generate all the info
        download_link = make_download_link('firefox', build, version,
                                           platform, locale)
        download_link_direct = make_download_link('firefox', build, version,
                                                  platform, locale, True)
        builds.append({'platform': platform,
                       'platform_pretty': platform_pretty,
                       'download_link': download_link,
                       'download_link_direct': download_link_direct})

    # Get the native name for current locale
    langs = product_details.languages
    locale_name = langs[locale]['native'] if locale in langs else locale

    data = {
        'locale_name': locale_name,
        'version': version,
        'product': 'firefox',
        'builds': builds,
        'id': id
    }

    html = jingo.render_to_string(ctx['request'],
                                  'mozorg/download_button_%s.html' % format,
                                  data)
    return jinja2.Markup(html)


@jingo.register.function
@jinja2.contextfunction
def mobile_download_button(ctx, id, platform, build=None):
    locale = ctx['request'].locale
    url = ''

    if platform == 'android':
        if build == 'beta':
            url = 'market://details?id=org.mozilla.firefox_beta'
        else:
            url = 'market://details?id=org.mozilla.firefox'
    elif platform == 'desktop' and build == 'beta':
        # this part is temporary for now until we figure out how to
        # manage all this for mobile
        url = 'https://market.android.com/details?id=org.mozilla.firefox_beta'
    else:
        raise 'Unsupported platform for mobile download button'

    html = jingo.render_to_string(ctx['request'],
                                  'mozorg/download_button_mobile.html',
                                  {'id': id,
                                   'download_link': url})
    return jinja2.Markup(html)


@jingo.register.function
@jinja2.contextfunction
def php_url(ctx, url):
    """Process a URL on the PHP site and prefix the locale to it."""
    locale = getattr(ctx['request'], 'locale', None)

    # Do this only if we have a locale and the URL is absolute
    if locale and url[0] == '/':
        return path.join('/', locale, url.lstrip('/'))
    return url


@jingo.register.function
def url(viewname, *args, **kwargs):
    """Helper for Django's ``reverse`` in templates."""
    url = reverse(viewname, args=args, kwargs=kwargs)
    # If this instance is a mix of Python and PHP, it can be set to
    # force the /b/ URL so that linking across pages work
    # TURNED OFF FOR NOW. The dev site seems to be doing this already
    # somehow. Looking into it. Issue #22
    if getattr(settings, 'FORCE_SLASH_B', False) and False:
        return path.join('/b/', url.lstrip('/'))
    return url


@jingo.register.function
def media(url):
    return path.join(settings.MEDIA_URL, url.lstrip('/'))


@jingo.register.function
def field_with_attrs(bfield, **kwargs):
    """Allows templates to dynamically add html attributes to bound
    fields from django forms"""
    bfield.field.widget.attrs.update(kwargs)
    return bfield


@jingo.register.function
def platform_img(url, **kwargs):
    attrs = ' '.join(('%s="%s"' % (attr, val)
                      for attr, val in kwargs.items()))
    url = path.join(settings.MEDIA_URL, url.lstrip('/'))

    # Don't download any image until the javascript sets it based on
    # data-src so we can to platform detection. If no js, show the
    # windows version.
    markup = ('<img class="platform-img js" src="" data-src="%s" %s>'
              '<noscript><img class="platform-img win" src="%s" %s></noscript>'
              % (url, attrs, url, attrs))

    return jinja2.Markup(markup)


@jingo.register.function
def video(*args, **kwargs):
    """
    HTML5 Video tag helper.

    Accepted kwargs:
    prefix, w, h, autoplay

    Use like this:
    {{ video('http://example.com/myvid.mp4', http://example.com/myvid.webm',
             w=640, h=360) }}

    You can also use a prefix like:
    {{ video('myvid.mp4', 'myvid.webm', prefix='http://example.com') }}

    Finally, MIME type detection happens by file extension. Supported: webm,
    mp4, ogv. If you want anything else, patches welcome.
    """

    filetypes = ('webm', 'ogv', 'mp4')
    mime = {'webm': 'video/webm',
            'ogv': 'video/ogg; codecs="theora, vorbis"',
            'mp4': 'video/mp4'}

    videos = {}
    for v in args:
        try:
            ext = v.rsplit('.', 1)[1].lower()
        except IndexError:
            # TODO: Perhaps we don't want to swallow this quietly in the future.
            continue
        if ext not in filetypes:
            continue
        videos[ext] = (v if not 'prefix' in kwargs else
                       urlparse.urljoin(kwargs['prefix'], v))

    if not videos:
        return ''

    # defaults
    data = {
        'w': 640,
        'h': 360,
        'autoplay': False,
    }

    # Flash fallback, if mp4 file on Mozilla Videos CDN.
    data['flash_fallback'] = False
    if 'mp4' in videos:
        mp4_url = urlparse.urlparse(videos['mp4'])
        if mp4_url.netloc.lower() in ('videos.mozilla.org', 'videos-cdn.mozilla.net'):
            data['flash_fallback'] = mp4_url.path

    data.update(**kwargs)
    data.update(filetypes=filetypes, mime=mime, videos=videos)

    return jinja2.Markup(jingo.env.get_template(
        'mozorg/videotag.html').render(**data))
