"""
Helpers for handling CURRI XACML webhook requests.
"""
from typing import Dict, Optional
import xml.etree.ElementTree as ET


def _match_attr_id(attr_id: str, needle: str) -> bool:
    hay = (attr_id or "").lower()
    return needle in hay


def parse_xacml_request(xml_text: str) -> Dict[str, Optional[str]]:
    """
    Parses XACML XML and extracts called/calling numbers and transformed CDPN.
    """
    called_number = None
    calling_number = None
    transformedcdpn = None

    root = ET.fromstring(xml_text)
    for attr in root.iter():
        if not attr.tag.endswith("Attribute"):
            continue
        attr_id = attr.attrib.get("AttributeId") or attr.attrib.get("AttributeID") or ""
        values = []
        for val in attr.findall(".//{*}AttributeValue"):
            if val.text:
                values.append(val.text.strip())
        if not values:
            continue

        if _match_attr_id(attr_id, "callednumber") or _match_attr_id(attr_id, "calledparty"):
            called_number = values[0]
        if _match_attr_id(attr_id, "callingnumber") or _match_attr_id(attr_id, "callingparty"):
            calling_number = values[0]
        if _match_attr_id(attr_id, "transformedcdpn"):
            transformedcdpn = values[0]

    return {
        "called_number": called_number,
        "calling_number": calling_number,
        "transformedcdpn": transformedcdpn,
    }


def build_continue_response() -> str:
    """
    Returns a XACML <continue> response body.
    """
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Response xmlns="urn:oasis:names:tc:xacml:2.0:policy:schema:os">'
        '<Result>'
        '<Decision>Permit</Decision>'
        '<Obligations>'
        '<Obligation ObligationId="continue" FulfillOn="Permit"/>'
        '</Obligations>'
        '</Result>'
        '</Response>'
    )
