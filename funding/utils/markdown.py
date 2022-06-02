from bs4 import BeautifulSoup
from collections import namedtuple
from jinja2 import Markup, escape
from urllib.parse import urljoin
from pygments import highlight
from pygments.formatters import ClassNotFound
from pygments.formatters.html import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from urllib.parse import urlparse, urlunparse
import bleach
import html
import mistletoe as m
from mistletoe.span_token import SpanToken, RawText
import re


MARKDOWN_PROPOSAL_DEFAULT = """
## Why?

What problem(s) are you trying to solve?

## How much?

What is the total cost? List expenses per item. Total hours of work and per hour rate. What exchange rates are you using?

## What?

Describe your idea in detail.

## Milestones?

Break down tasks into different stages. Each stage should have the estimated number of days/weeks needed and cost per stage.

## Outcomes?

What will be delivered? What goals will be reached?

## Why you?

What skills and experience do you have?
""".strip()


SRHT_MARKDOWN_VERSION = 12


class PlainLink(SpanToken):
    """
    Plain link and mail tokens. ("http://www.google.com" and "test@example.org")

    Attributes:
        children (iterator): a single RawText node for alternative text.
        target (str): link target.
    """
    pattern = re.compile(r"(?<!\\)(?:\\\\)*" # Fail if prefixed by odd number of backslashes
            r"((?P<url>[A-Za-z][A-Za-z0-9+.-]{1,31}://[^ \t\n\r\f\v<>]*)" # URLs: 'scheme'://'path'
            r"|(?P<mail>[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9]" # Emails: 'user'@'domain
                r"(?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
                r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+))")
    parse_inner = False
    precedence = 3

    def __init__(self, match):
        content = match.group(1)
        self.children = (RawText(content),)
        self.target = content
        self.mailto = match.group("mail") is not None


class SrhtRenderer(m.HTMLRenderer):
    def __init__(self, link_prefix=None, baselevel=1):
        super().__init__(PlainLink)
        self.baselevel = baselevel
        if isinstance(link_prefix, (tuple, list)):
            # If passing a 2 item list/tuple than assume the second
            # item is to be used to fetch raw_blob url's (ie, images)
            try:
                self.link_prefix, self.blob_prefix = link_prefix
            except ValueError:
                self.link_prefix = link_prefix[0]
                self.blob_prefix = link_prefix[0]
        else:
            self.link_prefix = link_prefix
            self.blob_prefix = link_prefix

    def _relative_url(self, url, use_blob=False):
        p = urlparse(url)
        link_prefix = self.link_prefix if not use_blob else self.blob_prefix
        if not link_prefix:
            return url
        if not link_prefix.endswith("/"):
            link_prefix += "/"
        if not p.netloc and not p.scheme and link_prefix:
            path = urljoin(link_prefix, p.path)
            url = urlunparse(('', '', path, p.params, p.query, p.fragment))
        return url

    def render_link(self, token):
        template = '<a href="{target}"{title}>{inner}</a>'
        url = token.target
        if token.title:
            title = ' title="{}"'.format(self.escape_html(token.title))
        else:
            title = ''
        if not url.startswith("#"):
            url = self._relative_url(url)
        target = self.escape_url(url)

        for i in range(len(token.children)):
            if isinstance(token.children[i], PlainLink):
                token.children[i] = RawText(token.children[i].target)
        inner = self.render_inner(token)
        return template.format(target=target, title=title, inner=inner)

    def render_plain_link(self, token):
        template = '<a href="{target}">{inner}</a>'
        if token.mailto:
            target = 'mailto:{}'.format(token.target)
        else:
            target = self.escape_url(token.target)
        inner = self.render_inner(token)
        return template.format(target=target, inner=inner)

    def render_image(self, token):
        template = '<img src="{}" alt="{}"{} />'
        url = self._relative_url(token.src, use_blob=True)
        if token.title:
            title = ' title="{}"'.format(self.escape_html(token.title))
        else:
            title = ''
        alt = self.render_to_plain(token)
        return template.format(url, alt, title)

    def render_block_code(self, token):
        template = '<pre><code{attr}>{inner}</code></pre>'
        if token.language:
            try:
                lexer = get_lexer_by_name(token.language, stripall=True)
            except ClassNotFound:
                lexer = None
            if lexer:
                formatter = HtmlFormatter()
                return highlight(token.children[0].content, lexer, formatter)
            else:
                attr = ' class="{}"'.format('language-{}'.format(self.escape_html(token.language)))
        else:
            attr = ''
        inner = html.escape(token.children[0].content)
        return template.format(attr=attr, inner=inner)

    def render_heading(self, token):
        template = '<h{level} id="{_id}"><a href="#{_id}" aria-hidden="true">{inner}</a></h{level}>'
        level = token.level + self.baselevel
        if level > 6:
            level = 6
        inner = self.render_inner(token)
        _id = re.sub(r'[^a-z0-9-_]', '', inner.lower().replace(" ", "-"))
        return template.format(level=level, inner=inner, _id=_id)


def _img_filter(tag, name, value):
    if name in ["alt", "height", "width"]:
        return True
    if name == "src":
        p = urlparse(value)
        return p.scheme in ["http", "https", ""]
    return False


def _input_filter(tag, name, value):
    if name in ["checked", "disabled"]:
        return True
    return name == "type" and value in ["checkbox"]


def _wildcard_filter(tag, name, value):
    return name in ["style", "class", "colspan", "rowspan"]


_sanitizer_attrs = {
    "a": ["id", "href", "title"],
    "h1": ["id"],
    "h2": ["id"],
    "h3": ["id"],
    "h4": ["id"],
    "h5": ["id"],
    "h6": ["id"],
    "img": _img_filter,
    "input": _input_filter,
    "*": _wildcard_filter,
}
_sanitizer = bleach.sanitizer.Cleaner(
    tags=bleach.sanitizer.ALLOWED_TAGS + [
        "p", "div", "span", "pre", "hr",
        "dd", "dt", "dl",
        "table", "thead", "tbody", "tr", "th", "td",
        "input",
        "img",
        "q",
        "h1", "h2", "h3", "h4", "h5", "h6",
    ],
    attributes={**bleach.sanitizer.ALLOWED_ATTRIBUTES, **_sanitizer_attrs},
    protocols=[
        'ftp',
        'gemini',
        'gopher',
        'http',
        'https',
        'irc',
        'ircs',
        'mailto',
    ],
    styles=bleach.sanitizer.ALLOWED_STYLES + [
        "margin", "padding",
        "text-align", "font-weight", "text-decoration"
    ]
    + [f"padding-{p}" for p in ["left", "right", "bottom", "top"]]
    + [f"margin-{p}" for p in ["left", "right", "bottom", "top"]],
    strip=True)


def sanitize(html):
    return add_noopener(_sanitizer.clean(html))


def add_noopener(html):
    soup = BeautifulSoup(str(html), 'html.parser')
    for a in soup.findAll('a'):
        a['rel'] = 'nofollow noopener'
    return str(soup)


def generate_html(markdown, baselevel=1, link_prefix=None, with_styles=True) -> str:
    with SrhtRenderer(link_prefix, baselevel) as renderer:
        html = renderer.render(m.Document(markdown))
    formatter = HtmlFormatter()
    if with_styles:
        style = ".highlight { background: inherit; }"
        return Markup(f"<style>{style}</style>"
                + "<div class='markdown'>"
                + sanitize(html)
                + "</div>")
    else:
        return Markup(sanitize(html))


Heading = namedtuple("Header", ["level", "name", "id", "children", "parent"])


def extract_toc(markup):
    soup = BeautifulSoup(str(markup), "html5lib")
    cur = top = Heading(
        level=0, children=list(),
        name=None, id=None, parent=None
    )
    for el in soup.descendants:
        try:
            level = ["h1", "h2", "h3", "h4", "h5", "h6"].index(el.name)
        except ValueError:
            continue
        while cur.level >= level:
            cur = cur.parent
        if el.a:
            el.a.extract()
        heading = Heading(
            level=level, name=el.text,
            id=el.attrs.get("id"),
            children=list(),
            parent=cur
        )
        cur.children.append(heading)
        cur = heading
    return top.children
