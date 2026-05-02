"""Form 4 XML parser tests using a synthetic minimal filing."""

from __future__ import annotations

from insider_bot import edgar


FORM4_XML = b"""<?xml version="1.0"?>
<ownershipDocument>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerCik>0001234567</rptOwnerCik>
      <rptOwnerName>Doe, Jane</rptOwnerName>
    </reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>1</isDirector>
      <isOfficer>1</isOfficer>
      <isTenPercentOwner>0</isTenPercentOwner>
      <officerTitle>Chief Financial Officer</officerTitle>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2024-03-15</value></transactionDate>
      <transactionCoding>
        <transactionCode>P</transactionCode>
      </transactionCoding>
      <transactionAmounts>
        <transactionShares><value>500</value></transactionShares>
        <transactionPricePerShare><value>123.45</value></transactionPricePerShare>
      </transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionDate><value>2024-03-15</value></transactionDate>
      <transactionCoding>
        <transactionCode>S</transactionCode>
      </transactionCoding>
      <transactionAmounts>
        <transactionShares><value>100</value></transactionShares>
        <transactionPricePerShare><value>120</value></transactionPricePerShare>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>
"""


def test_parse_form4_extracts_only_purchases():
    txns = edgar.parse_form4(
        FORM4_XML,
        accession="0001234567-24-000001",
        ticker="AAA",
        cik="1234567",
        filing_date="2024-03-17",
    )
    assert len(txns) == 1
    t = txns[0]
    assert t.code == "P"
    assert t.ticker == "AAA"
    assert t.owner_name == "Doe, Jane"
    assert t.is_director is True
    assert t.is_officer is True
    assert t.is_ten_percent is False
    assert t.shares == 500.0
    assert t.price == 123.45
    assert t.value == 500.0 * 123.45
    assert t.transaction_date == "2024-03-15"
    assert t.filing_date == "2024-03-17"


def test_parse_form4_handles_malformed_xml():
    assert edgar.parse_form4(
        b"<not-valid-xml",
        accession="x", ticker="x", cik="x", filing_date="2024-01-01",
    ) == []
