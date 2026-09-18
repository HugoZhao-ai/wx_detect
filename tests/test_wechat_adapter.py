from wx_trade_alert.wechat_adapter import _split_group_sender


def test_split_group_sender_extracts_wechat_4_sender_prefix():
    sender, content = _split_group_sender(
        "wxid_0jklpgevus6m22:\n都很正常，没所谓的，挣钱挣钱就行了。"
    )
    assert sender == "wxid_0jklpgevus6m22"
    assert content == "都很正常，没所谓的，挣钱挣钱就行了。"


def test_split_group_sender_leaves_plain_content_unchanged():
    sender, content = _split_group_sender("买两手 NVDA 150 call")
    assert sender == ""
    assert content == "买两手 NVDA 150 call"
