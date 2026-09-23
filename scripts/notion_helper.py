import logging
import os
import re
import time
from datetime import timedelta

from notion_client import Client
from retrying import retry

from utils import (
    format_date,
    get_date,
    get_first_and_last_day_of_month,
    get_first_and_last_day_of_week,
    get_first_and_last_day_of_year,
    get_icon,
    get_number,
    get_property_value,
    get_relation,
    get_rich_text,
    get_title,
    timestamp_to_date,
)

TAG_ICON_URL = "https://www.notion.so/icons/tag_gray.svg"
USER_ICON_URL = "https://www.notion.so/icons/user-circle-filled_gray.svg"
TARGET_ICON_URL = "https://www.notion.so/icons/target_red.svg"
BOOKMARK_ICON_URL = "https://www.notion.so/icons/bookmark_gray.svg"


class NotionHelper:
    database_name_dict = {
        "TIME_DATABASE_NAME": "时间记录",
        "DAY_DATABASE_NAME": "日",
        "WEEK_DATABASE_NAME": "周",
        "MONTH_DATABASE_NAME": "月",
        "YEAR_DATABASE_NAME": "年",
        "ALL_DATABASE_NAME": "全部",
        "CLIENT_DATABASE_NAME": "Client",
        "PROJECT_DATABASE_NAME": "Project",
        "TAG_DATABASE_NAME": "标签",
    }
    database_id_dict = {}
    image_dict = {}

    def __init__(self):
        self.client = Client(auth=os.getenv("NOTION_TOKEN"), log_level=logging.ERROR)
        self.__cache = {}
        self.__data_source_cache = {}  # 缓存 database_id 到 data_source_id 的映射
        self.heatmap_block_id = None

        self.page_id = self.extract_page_id(os.getenv("NOTION_PAGE"))
        self.search_database(self.page_id)

        for key in self.database_name_dict.keys():
            if os.getenv(key):
                self.database_name_dict[key] = os.getenv(key)

        self.time_database_id = self.database_id_dict.get(
            self.database_name_dict.get("TIME_DATABASE_NAME")
        )
        self.day_database_id = self.database_id_dict.get(
            self.database_name_dict.get("DAY_DATABASE_NAME")
        )
        self.week_database_id = self.database_id_dict.get(
            self.database_name_dict.get("WEEK_DATABASE_NAME")
        )
        self.month_database_id = self.database_id_dict.get(
            self.database_name_dict.get("MONTH_DATABASE_NAME")
        )
        self.year_database_id = self.database_id_dict.get(
            self.database_name_dict.get("YEAR_DATABASE_NAME")
        )
        self.all_database_id = self.database_id_dict.get(
            self.database_name_dict.get("ALL_DATABASE_NAME")
        )
        self.client_database_id = self.database_id_dict.get(
            self.database_name_dict.get("CLIENT_DATABASE_NAME")
        )
        self.project_database_id = self.database_id_dict.get(
            self.database_name_dict.get("PROJECT_DATABASE_NAME")
        )
        self.tag_database_id = self.database_id_dict.get(
            self.database_name_dict.get("TAG_DATABASE_NAME")
        )

        if self.time_database_id:
            self.write_database_id(self.time_database_id)

    def get_data_source_id(self, database_id: str) -> str:
        """获取 database_id 对应的 data_source_id 并进行本地缓存"""
        if database_id in self.__data_source_cache:
            return self.__data_source_cache[database_id]

        db_info = self.client.databases.retrieve(database_id=database_id)
        data_sources = db_info.get("data_sources", [])
        if not data_sources:
            raise ValueError(f"Database {database_id} 没有绑定的 data_source")

        data_source_id = data_sources[0]["id"]
        self.__data_source_cache[database_id] = data_source_id
        return data_source_id

    def write_database_id(self, database_id):
        env_file = os.getenv("GITHUB_ENV")
        if env_file:
            with open(env_file, "a") as file:
                file.write(f"DATABASE_ID={database_id}\n")

    def extract_page_id(self, notion_url):
        if not notion_url:
            raise Exception("NOTION_PAGE 环境变量未设置")
        match = re.search(
            r"([a-f0-9]{32}|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})",
            notion_url,
        )
        if match:
            return match.group(0)
        raise Exception("获取 NotionID 失败，请检查输入的 Url 是否正确")

    def search_database(self, block_id):
        children = self.client.blocks.children.list(block_id=block_id).get("results", [])
        for child in children:
            child_type = child.get("type")
            if child_type == "child_database":
                title = child.get("child_database", {}).get("title")
                if title:
                    self.database_id_dict[title] = child.get("id")
            elif child_type == "embed" and child.get("embed", {}).get("url"):
                if child.get("embed").get("url").startswith("https://heatmap.malinkang.com/"):
                    self.heatmap_block_id = child.get("id")

            if child.get("has_children"):
                self.search_database(child["id"])

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def update_heatmap(self, block_id, url):
        return self.client.blocks.update(block_id=block_id, embed={"url": url})

    def get_week_relation_id(self, date):
        year, week, _ = date.isocalendar()
        week_str = f"{year}年第{week}周"
        start, end = get_first_and_last_day_of_week(date)
        properties = {"日期": get_date(format_date(start), format_date(end))}
        return self.get_relation_id(
            week_str, self.week_database_id, get_icon(TARGET_ICON_URL), properties
        )

    def get_month_relation_id(self, date):
        month_str = f"{date.year}年{date.month}月"
        start, end = get_first_and_last_day_of_month(date)
        properties = {"日期": get_date(format_date(start), format_date(end))}
        return self.get_relation_id(
            month_str, self.month_database_id, get_icon(TARGET_ICON_URL), properties
        )

    def get_year_relation_id(self, date):
        year_str = date.strftime("%Y")
        start, end = get_first_and_last_day_of_year(date)
        properties = {"日期": get_date(format_date(start), format_date(end))}
        return self.get_relation_id(
            year_str, self.year_database_id, get_icon(TARGET_ICON_URL), properties
        )

    def get_day_relation_id(self, date):
        new_date = date.replace(hour=0, minute=0, second=0, microsecond=0)
        day_str = new_date.strftime("%Y年%m月%d日")
        properties = {
            "日期": get_date(format_date(date)),
            "年": get_relation([self.get_year_relation_id(new_date)]),
            "月": get_relation([self.get_month_relation_id(new_date)]),
            "周": get_relation([self.get_week_relation_id(new_date)]),
        }
        return self.get_relation_id(
            day_str, self.day_database_id, get_icon(TARGET_ICON_URL), properties
        )

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def get_relation_id(self, name, id, icon, properties=None):
        """查找或创建关联 ID，使用新版 Data Sources 查询接口"""
        if properties is None:
            properties = {}
        key = f"{id}{name}"
        if key in self.__cache:
            return self.__cache[key]

        query_filter = {"property": "标题", "title": {"equals": name}}
        response = self.query(database_id=id, filter=query_filter)

        results = response.get("results", [])
        if not results:
            parent = {"database_id": id, "type": "database_id"}
            properties["标题"] = get_title(name)
            page_id = self.client.pages.create(
                parent=parent, properties=properties, icon=icon
            ).get("id")
        else:
            page_id = results[0].get("id")

        self.__cache[key] = page_id
        return page_id

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def update_book_page(self, page_id, properties):
        return self.client.pages.update(page_id=page_id, properties=properties)

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def update_page(self, page_id, properties):
        return self.client.pages.update(page_id=page_id, properties=properties)

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def create_page(self, parent, properties, icon):
        return self.client.pages.create(parent=parent, properties=properties, icon=icon)

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def query(self, **kwargs):
        """新版 Data Sources 通用查询封装"""
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        db_id = kwargs.pop("database_id", None)
        
        if db_id and "data_source_id" not in kwargs:
            kwargs["data_source_id"] = self.get_data_source_id(db_id)

        return self.client.data_sources.query(**kwargs)

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def get_block_children(self, id):
        response = self.client.blocks.children.list(block_id=id)
        return response.get("results", [])

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def append_blocks(self, block_id, children):
        return self.client.blocks.children.append(block_id=block_id, children=children)

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def append_blocks_after(self, block_id, children, after):
        return self.client.blocks.children.append(
            block_id=block_id, children=children, after=after
        )

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def delete_block(self, block_id):
        return self.client.blocks.delete(block_id=block_id)

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def query_all_by_book(self, database_id, filter):
        """使用新版 query 查询特定条件的所有分页数据"""
        results = []
        has_more = True
        start_cursor = None
        while has_more:
            response = self.query(
                database_id=database_id,
                filter=filter,
                start_cursor=start_cursor,
                page_size=100,
            )
            start_cursor = response.get("next_cursor")
            has_more = response.get("has_more")
            results.extend(response.get("results", []))
        return results

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def query_all(self, database_id):
        """使用新版 query 获取 database 中所有的数据"""
        results = []
        has_more = True
        start_cursor = None
        while has_more:
            response = self.query(
                database_id=database_id,
                start_cursor=start_cursor,
                page_size=100,
            )
            start_cursor = response.get("next_cursor")
            has_more = response.get("has_more")
            results.extend(response.get("results", []))
        return results

    def get_date_relation(self, properties, date):
        properties["年"] = get_relation([self.get_year_relation_id(date)])
        properties["月"] = get_relation([self.get_month_relation_id(date)])
        properties["周"] = get_relation([self.get_week_relation_id(date)])
        properties["日"] = get_relation([self.get_day_relation_id(date)])
        properties["全部"] = get_relation(
            [
                self.get_relation_id(
                    "全部",
                    id=self.all_database_id,
                    icon=get_icon(TARGET_ICON_URL),
                )
            ]
        )
