"""XMLTV EPG parser using lxml for efficient XML handling."""

import logging

from lxml import etree

logger = logging.getLogger(__name__)


def parse_xmltv(content: str) -> etree._Element:
    """Parse an XMLTV string into an lxml element tree root.

    Parameters
    ----------
    content:
        The raw XMLTV XML string.

    Returns
    -------
    etree._Element
        The root ``<tv>`` element of the parsed XMLTV document.

    Raises
    ------
    etree.XMLSyntaxError
        If the content is not valid XML.
    """
    parser = etree.XMLParser(resolve_entities=False, no_network=True, dtd_validation=False)
    root = etree.fromstring(content.encode("utf-8"), parser=parser)
    logger.debug("Parsed XMLTV document with tag <%s>", root.tag)
    return root


def get_programmes(tree: etree._Element) -> list[etree._Element]:
    """Get all ``<programme>`` elements from an XMLTV tree.

    Parameters
    ----------
    tree:
        The root element of a parsed XMLTV document.

    Returns
    -------
    list[etree._Element]
        All programme elements found in the tree.
    """
    programmes = tree.findall(".//programme")
    logger.debug("Found %d programme elements", len(programmes))
    return programmes


def get_channels(tree: etree._Element) -> list[dict]:
    """Extract channel information from an XMLTV tree.

    Parameters
    ----------
    tree:
        The root element of a parsed XMLTV document.

    Returns
    -------
    list[dict]
        Each dict contains: ``id`` (str), ``name`` (str | None),
        ``icon`` (str | None).
    """
    channels: list[dict] = []

    for ch_elem in tree.findall(".//channel"):
        channel_id = ch_elem.get("id", "")

        # Channel name from <display-name>
        display_name_elem = ch_elem.find("display-name")
        name = display_name_elem.text if display_name_elem is not None else None

        # Channel icon from <icon src="...">
        icon_elem = ch_elem.find("icon")
        icon = icon_elem.get("src") if icon_elem is not None else None

        channels.append({
            "id": channel_id,
            "name": name,
            "icon": icon,
        })

    logger.debug("Extracted %d channels from XMLTV", len(channels))
    return channels
