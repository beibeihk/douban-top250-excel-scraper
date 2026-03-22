from bs4 import BeautifulSoup

from douban_top250_to_excel import parse_info_block, parse_list_item


def test_parse_list_item_extracts_core_fields() -> None:
    html = """
    <tr class="item">
      <td>
        <a class="nbg" href="https://book.douban.com/subject/1007305/">
          <img src="https://img1.doubanio.com/view/subject/s/public/s1070959.jpg"/>
        </a>
      </td>
      <td>
        <div class="pl2">
          <a href="https://book.douban.com/subject/1007305/" title="红楼梦">红楼梦</a>
        </div>
        <p class="pl">[清] 曹雪芹 著 / 人民文学出版社 / 1996-12 / 59.70元</p>
        <div class="star clearfix">
          <span class="rating_nums">9.7</span>
          <span class="pl">(460771人评价)</span>
        </div>
        <p class="quote"><span class="inq">值得反复阅读。</span></p>
      </td>
    </tr>
    """
    soup = BeautifulSoup(html, "lxml")
    item = soup.select_one("tr.item")
    assert item is not None

    parsed = parse_list_item(item, rank=1)
    assert parsed["rank"] == "1"
    assert parsed["subject_id"] == "1007305"
    assert parsed["title"] == "红楼梦"
    assert parsed["book_url"] == "https://book.douban.com/subject/1007305/"
    assert parsed["rating"] == "9.7"
    assert parsed["rating_count"] == "460771"
    assert parsed["list_meta_raw"] == "[清] 曹雪芹 著 / 人民文学出版社 / 1996-12 / 59.70元"
    assert parsed["quote"] == "值得反复阅读。"


def test_parse_info_block_extracts_key_values() -> None:
    html = """
    <div id="info">
      <span class="pl">作者:</span> [清] 曹雪芹 著 / 高鹗<br/>
      <span class="pl">出版社:</span> 人民文学出版社<br/>
      <span class="pl">出版年:</span> 1996-12<br/>
      <span class="pl">页数:</span> 1606<br/>
      <span class="pl">定价:</span> 59.70元<br/>
      <span class="pl">装帧:</span> 平装<br/>
      <span class="pl">ISBN:</span> 9787020002207<br/>
    </div>
    """
    soup = BeautifulSoup(html, "lxml")
    info = soup.select_one("#info")
    assert info is not None

    info_raw, fields = parse_info_block(info)
    assert "作者" in info_raw
    assert fields["作者"] == "[清] 曹雪芹 著 / 高鹗"
    assert fields["出版社"] == "人民文学出版社"
    assert fields["出版年"] == "1996-12"
    assert fields["页数"] == "1606"
    assert fields["定价"] == "59.70元"
    assert fields["装帧"] == "平装"
    assert fields["ISBN"] == "9787020002207"
