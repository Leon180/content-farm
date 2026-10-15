"""HTTP status of youtube.com/@<handle> for each handle (404 = unclaimed or hidden)."""
import sys
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 Chrome/126 Safari/537.36"
for handle in sys.argv[1:]:
    url = "https://www.youtube.com/@" + urllib.parse.quote(handle)
    try:
        code = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=20).status
    except urllib.error.HTTPError as exc:
        code = exc.code
    except Exception as exc:  # network error: report verbatim
        code = repr(exc)
    print(handle, code, flush=True)
