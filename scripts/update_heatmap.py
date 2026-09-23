import argparse
import os
from utils import get_embed
from notion_helper import NotionHelper

def get_file():
    # 设置文件夹路径
    folder_path = './OUT_FOLDER'
    # 检查文件夹是否存在
    if os.path.exists(folder_path) and os.path.isdir(folder_path):
        entries = os.listdir(folder_path)
        print(f"OUT_FOLDER 文件列表: {entries}")
        file_name = entries[0] if entries else None
        print(f"找到图片文件: {file_name}")
        return file_name
    else:
        print("OUT_FOLDER does not exist.")
        return None
    
if __name__ == "__main__":
    notion_helper = NotionHelper()
    image_file = get_file()
    if image_file:
        image_url = f"https://raw.githubusercontent.com/{os.getenv('REPOSITORY')}/{os.getenv('REF').split('/')[-1]}/OUT_FOLDER/{image_file}"
        heatmap_url = f"https://heatmap.malinkang.com/?image={image_url}"
        print(f"图片raw地址: {image_url}")
        print(f"热力图完整embed地址: {heatmap_url}")
        if notion_helper.heatmap_block_id:
            print(f"✅ 找到heatmap_block_id={notion_helper.heatmap_block_id}, 执行更新块")
            response = notion_helper.update_heatmap(
                block_id=notion_helper.heatmap_block_id, url=heatmap_url
            )
            print(f"update_heatmap 返回: {response}")
        else:
            print("⚠️ heatmap_block_id为空，执行append新增embed块")
            response = notion_helper.append_blocks(
                block_id=notion_helper.page_id, children=[get_embed(heatmap_url)]
            )
            print(f"append_blocks 返回: {response}")
            # 【关键】从返回结果拿到新块ID，保存！下次就可以直接update，不再新增
            # response["appended"][0]["id"] 就是新建embed块的block_id
            if response and response.get("appended"):
                new_block_id = response["appended"][0]["id"]
                print(f"🎉 新增embed成功，新block_id={new_block_id}")
                # 你需要把 new_block_id 持久化保存（写入github env或者notion页面属性）
                # 下一次运行读取这个id赋值给 notion_helper.heatmap_block_id
    else:
        print("❌ 没有找到图片文件，跳过同步")
