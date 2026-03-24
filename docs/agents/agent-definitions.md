# 24个数字员工岗位详细定义

## 核心运营岗位 (1-13)

### 1. 总监 Agent (Director)

**角色定位**: 全局决策者，制定策略，协调各岗位

**职责**:
- 制定每日/每周选品策略
- 分配任务给各岗位
- 监控整体运营指标
- 处理异常情况升级
- 审批高风险决策

**工具**:
- Odoo数据查询
- LangGraph状态查看
- Redis任务队列管理
- 企业微信/钉钉通知

**输入**:
- 历史销售数据
- 库存状况
- 市场趋势报告
- 人工指令

**输出**:
- 选品策略文档
- 任务分配指令
- 审批决策

**自主模式**:
- 每日8:00分析前日数据
- 制定当日选品计划
- 自动分配任务

**响应模式**:
- Webhook接收人工指令
- 实时调整策略
- 紧急任务插队

---

### 2. 选品 Agent (Product Selector)

**角色定位**: 市场分析师，发现潜力商品

**职责**:
- 爬取目标平台热销数据
- 在1688匹配货源
- 计算初步利润
- 推荐候选商品

**工具**:
- Playwright (爬虫)
- 1688开放平台API
- BGE-M3 (向量匹配)
- Qwen3.5 (数据分析)

**输入**:
- 总监的选品策略
- 目标平台 (Temu/Amazon等)
- 品类、价格区间

**输出**:
- 候选商品列表 (JSON)
- 竞品数据
- 1688货源链接

**关键逻辑**:
```python
def select_products(strategy):
    # 1. 爬取目标平台
    hot_products = crawl_platform(
        platform=strategy.platform,
        category=strategy.category,
        sort_by="sales",
        limit=100
    )

    # 2. 过滤条件
    filtered = filter_products(
        hot_products,
        price_range=strategy.price_range,
        min_sales=strategy.min_sales,
        min_rating=4.0
    )

    # 3. 1688货源匹配
    for product in filtered:
        suppliers = match_1688_suppliers(
            product.title,
            product.image,
            method="vector_search"  # 或 "image_search"
        )
        product.suppliers = suppliers[:10]

    # 4. 初步利润计算
    for product in filtered:
        product.estimated_profit = calculate_profit(
            selling_price=product.price,
            cost=product.suppliers[0].price,
            shipping=estimate_shipping(product.weight),
            commission=get_platform_commission(strategy.platform)
        )

    # 5. 排序推荐
    return sorted(filtered, key=lambda x: x.estimated_profit, reverse=True)[:20]
```

**并发能力**: 50个商品同时分析

---

### 3. 图像复刻 Agent (Image Replicator)

**角色定位**: 视觉设计师，生成差异化商品图

**职责**:
- 分析竞品图片风格
- 生成差异化Prompt
- 调用ComfyUI生成图片
- 质量检测

**工具**:
- Qwen2-VL (视觉理解)
- ComfyUI API
- FLUX.2 dev
- ControlNet

**输入**:
- 竞品图片URL
- 商品基本信息
- 品牌调性要求

**输出**:
- 主图 2张 (1024x1024)
- 详情页图 8张 (800x1200)
- 图片存储路径

**关键逻辑**:
```python
def replicate_images(product):
    # 1. 分析竞品图片
    analysis = qwen2_vl.analyze(product.competitor_images)
    # 输出: {
    #   "background": "pure white",
    #   "angle": "45 degree",
    #   "lighting": "soft light",
    #   "style": "minimalist"
    # }

    # 2. 生成差异化Prompt
    prompts = generate_differentiated_prompts(analysis)
    # 主图1: "light gray gradient background, front view, warm tone"
    # 主图2: "lifestyle scene, product in use, natural lighting"
    # 详情页1-8: 细节、尺寸、场景等

    # 3. 调用ComfyUI
    images = []
    for prompt in prompts:
        image = comfyui_api.generate(
            prompt=prompt,
            model="flux2-dev-fp8",
            width=1024,
            height=1024,
            controlnet=product.reference_image,  # 保持产品一致性
            steps=20,
            cfg_scale=7.5
        )
        images.append(image)

    # 4. 质量检测
    for img in images:
        score = qwen2_vl.quality_score(img)
        if score < 85:
            # 重新生成
            img = regenerate_with_feedback(img, score)

    # 5. 存储到Odoo filestore
    paths = save_to_filestore(images, product.sku)
    return paths
```

**性能**:
- 单套图片生成时间: 2.5分钟
- 并发数: 4 (4卡GPU)
- 日产能: 2304套

---

### 4. 配件挖掘 Agent (Accessory Finder)

**角色定位**: 商品策划师，挖掘配套商品

**职责**:
- 分析主商品
- 推荐配套商品
- 生成套装方案

**工具**:
- Qwen3.5 (推理)
- 1688 API (搜索配件)
- Odoo (查询已有商品)

**输入**:
- 主商品信息
- 1688商品详情

**输出**:
- 3-5个配套商品
- 套装定价建议

**关键逻辑**:
```python
def find_accessories(main_product):
    # 1. AI推理配件类型
    accessory_types = qwen3_5.infer(
        f"商品: {main_product.title}\n"
        f"请推荐3-5种配套商品类型，要求功能互补或场景关联"
    )
    # 输出: ["手机壳", "钢化膜", "充电器"]

    # 2. 在1688搜索
    accessories = []
    for acc_type in accessory_types:
        results = search_1688(
            keyword=f"{main_product.category} {acc_type}",
            price_range=(5, 50),
            sort_by="sales"
        )
        accessories.append(results[0])  # 取销量最高的

    # 3. 生成套装方案
    bundle = {
        "main": main_product,
        "accessories": accessories,
        "bundle_price": calculate_bundle_price(main_product, accessories),
        "discount": 0.15  # 套装优惠15%
    }

    return bundle
```

---

### 5. 多语文案 Agent (Multilingual Copywriter)

**角色定位**: 内容创作者，生成多语言营销文案

**职责**:
- 生成商品标题 (5种语言)
- 生成商品描述
- 生成卖点bullet points
- 生成HTML详情页

**工具**:
- Qwen3.5 (文案生成)
- 翻译模型 (NLLB-200)

**输入**:
- 商品信息
- 图片路径
- 目标语言列表

**输出**:
- 多语言文案JSON
- HTML详情页

**关键逻辑**:
```python
def generate_copy(product, languages=["en", "es", "ja", "ru", "pt"]):
    copies = {}

    for lang in languages:
        # 1. 生成标题
        title = qwen3_5.generate(
            f"为以下商品生成{lang}标题，60-80字符，包含核心关键词:\n"
            f"{product.description}"
        )

        # 2. 生成描述
        description = qwen3_5.generate(
            f"为以下商品生成{lang}详细描述，5段，每段50-80词:\n"
            f"段落1: 产品概述\n"
            f"段落2-3: 核心卖点\n"
            f"段落4: 使用场景\n"
            f"段落5: 规格参数"
        )

        # 3. 生成bullet points
        bullets = qwen3_5.generate(
            f"生成5-7个{lang}卖点，每个15-25词"
        )

        copies[lang] = {
            "title": title,
            "description": description,
            "bullets": bullets
        }

    # 4. 生成HTML详情页
    html = generate_html_template(copies, product.images)

    return copies, html
```

---

### 6. ERP入库 Agent (ERP Manager)

**角色定位**: 数据管理员，维护Odoo商品库

**职责**:
- 创建Odoo商品记录
- 生成SKU编码
- 关联图片/文案
- 设置定价策略

**工具**:
- Odoo XML-RPC API
- PostgreSQL (直接查询)

**输入**:
- 完整商品数据包

**输出**:
- Odoo商品ID
- SKU编码

**关键逻辑**:
```python
def create_odoo_product(product_data):
    # 1. 生成SKU
    sku = generate_sku(
        category=product_data.category,
        date=datetime.now(),
        sequence=get_next_sequence()
    )
    # 格式: CAT-20260318-001

    # 2. 创建Odoo商品
    product_id = odoo.create('product.product', {
        'name': product_data.title_en,
        'default_code': sku,
        'type': 'product',
        'categ_id': map_category(product_data.category),
        'list_price': product_data.selling_price,
        'standard_price': product_data.cost_price,
        'image_1920': base64_encode(product_data.main_image),
        'description_sale': product_data.description_en,
        'weight': product_data.weight,
        'volume': product_data.volume,
    })

    # 3. 关联多语言
    for lang, copy in product_data.copies.items():
        odoo.write('product.product', product_id, {
            'name': copy.title,
            'description_sale': copy.description
        }, context={'lang': lang})

    # 4. 关联图片到filestore
    for img_path in product_data.images:
        odoo.create('product.image', {
            'product_tmpl_id': product_id,
            'image_1920': read_from_filestore(img_path)
        })

    return product_id, sku
```

---

### 7. 核价 Agent (Pricing Analyst)

**角色定位**: 定价专家，动态调整价格

**职责**:
- 计算成本价
- 制定售价策略
- 监控竞品价格
- 动态调价

**工具**:
- Qwen3.5 (定价策略)
- 汇率API
- 竞品价格爬虫

**输入**:
- 商品成本数据
- 竞品价格
- 历史销售数据

**输出**:
- 各平台定价
- 促销建议

**关键逻辑**:
```python
def calculate_pricing(product):
    # 1. 成本计算
    total_cost = (
        product.purchase_price +
        product.shipping_cost +
        product.packaging_cost +
        product.platform_fee +
        product.payment_fee
    )

    # 2. 基础定价
    base_price = total_cost / (1 - target_profit_margin)

    # 3. 竞品价格分析
    competitor_prices = get_competitor_prices(product.category)
    avg_price = mean(competitor_prices)

    # 4. 定价策略
    if base_price < avg_price * 0.8:
        # 成本优势，定价略低于均价
        final_price = avg_price * 0.9
    elif base_price > avg_price * 1.2:
        # 成本劣势，放弃或找更便宜货源
        return None
    else:
        # 正常定价
        final_price = base_price * 1.1

    # 5. 汇率转换
    prices_by_platform = {}
    for platform in product.target_platforms:
        currency = get_platform_currency(platform)
        rate = get_exchange_rate("CNY", currency)
        prices_by_platform[platform] = final_price * rate

    return prices_by_platform
```

---

### 8. 风控 Agent (Risk Controller)

**角色定位**: 合规审查员，防范法律风险

**职责**:
- 侵权检测
- 合规审查
- 风险评分
- 异常告警

**工具**:
- Qwen2-VL (图像识别)
- 品牌词库
- 专利数据库API

**输入**:
- 商品信息
- 图片
- 目标市场

**输出**:
- 风险评分 (0-100)
- 风险项列表
- 处理建议

**关键逻辑**:
```python
def risk_assessment(product):
    risk_score = 0
    risk_items = []

    # 1. 品牌侵权检测
    brand_keywords = ["Nike", "Adidas", "Apple", "Samsung", ...]
    for keyword in brand_keywords:
        if keyword.lower() in product.title.lower():
            risk_score += 30
            risk_items.append(f"疑似侵权品牌: {keyword}")

    # 2. 图像相似度检测
    for img in product.images:
        similarity = compare_with_known_infringements(img)
        if similarity > 0.9:
            risk_score += 40
            risk_items.append("图片与已知侵权案例高度相似")

    # 3. 禁售品类检测
    forbidden_categories = ["武器", "药品", "烟草", ...]
    if product.category in forbidden_categories:
        risk_score += 50
        risk_items.append(f"禁售品类: {product.category}")

    # 4. 目标市场合规检测
    for market in product.target_markets:
        regulations = get_market_regulations(market)
        if not check_compliance(product, regulations):
            risk_score += 20
            risk_items.append(f"{market}市场合规问题")

    # 5. 风险等级
    if risk_score >= 70:
        decision = "拒绝"
    elif risk_score >= 40:
        decision = "人工审核"
    else:
        decision = "通过"

    return {
        "score": risk_score,
        "items": risk_items,
        "decision": decision
    }
```

---

### 9. RPA上架 Agent (Listing Automator)

**角色定位**: 运营执行者，自动化上架商品

**职责**:
- 登录各平台
- 填写商品信息
- 上传图片
- 提交发布

**工具**:
- Playwright
- 平台API (优先)

**输入**:
- Odoo商品ID
- 目标平台列表

**输出**:
- 平台商品ID
- 上架状态

**关键逻辑**:
```python
async def list_product(product, platform):
    # 1. 优先使用API
    if has_api(platform):
        return list_via_api(product, platform)

    # 2. RPA方式
    browser = await playwright.chromium.launch(headless=True)
    page = await browser.new_page()

    # 3. 登录
    await login(page, platform)

    # 4. 导航到发布页面
    await page.goto(get_listing_url(platform))

    # 5. 填写表单
    await page.fill('[name="title"]', product.title)
    await page.fill('[name="description"]', product.description)
    await page.select_option('[name="category"]', product.category_id)

    # 6. 上传图片
    for img_path in product.images:
        await page.set_input_files('[name="images"]', img_path)

    # 7. 设置价格/库存
    await page.fill('[name="price"]', str(product.price))
    await page.fill('[name="stock"]', str(product.stock))

    # 8. 提交
    await page.click('button[type="submit"]')

    # 9. 获取商品ID
    await page.wait_for_url('**/product/*')
    product_id = extract_product_id(page.url)

    await browser.close()
    return product_id
```

---

### 10. 验证码处理 Agent (CAPTCHA Solver)

**角色定位**: 技术支持，处理验证码

**职责**:
- 监听验证码事件
- 自动识别验证码
- 人工处理兜底

**工具**:
- 2Captcha API
- Qwen2-VL (点选验证码)
- Redis Pub/Sub (事件监听)

**输入**:
- 验证码图片
- 验证码类型

**输出**:
- 验证码答案

**关键逻辑**:
```python
def solve_captcha(captcha_image, captcha_type):
    if captcha_type == "text":
        # 文字验证码 → 2Captcha
        result = captcha_api.solve_text(captcha_image)

    elif captcha_type == "slider":
        # 滑块验证码 → 轨迹模拟
        result = simulate_slider_trajectory(captcha_image)

    elif captcha_type == "click":
        # 点选验证码 → Qwen2-VL
        instruction = extract_instruction(captcha_image)
        # "请点击所有的猫"
        positions = qwen2_vl.detect_objects(captcha_image, instruction)
        result = positions

    else:
        # 未知类型 → 人工处理
        result = request_human_help(captcha_image)

    return result

# Redis事件监听
def listen_captcha_events():
    pubsub = redis.pubsub()
    pubsub.subscribe('captcha_channel')

    for message in pubsub.listen():
        if message['type'] == 'message':
            data = json.loads(message['data'])
            answer = solve_captcha(data['image'], data['type'])
            redis.publish(f"captcha_answer_{data['task_id']}", answer)
```

---

### 11-13. QA、客服、广告短视频 Agent

(篇幅限制，简要说明)

**11. QA Agent**: 质量检测，审核图片/文案/商品信息
**12. 客服 Agent**: 多语言智能客服，处理买家咨询
**13. 广告短视频 Agent**: 生成商品短��频，用于TikTok/抖音推广

---

## 内容营销岗位 (14-16)

### 14. 广告投放 Agent
- 对接Temu Ads、Google Ads、Facebook Ads
- 自动创建广告系列
- 优化出价策略

### 15. 短视频生成 Agent
- 调用视频生成AI (如Runway、Pika)
- 生成15-60秒商品短视频
- 添加字幕、背景音乐

### 16. 竞品分析 Agent
- 监控竞品价格、销量、评价
- 分析竞品策略
- 生成竞争情报报告

---

## KOL岗位 (17-19)

### 17. KOL筛选 Agent
- 爬取TikTok/YouTube/Instagram KOL数据
- 分析粉丝画像、互动率
- 推荐合适KOL

### 18. 内容策划 Agent
- 生成KOL合作Brief
- 设计内容脚本
- 提供素材包

### 19. 效果追踪 Agent
- 监控KOL视频数据
- 计算ROI
- 优化合作策略

---

## 采购供应链岗位 (20-24)

### 20. 1688采购 Agent
- 生成采购单
- 调用支付宝API付款
- 跟踪采购状态

### 21. 物流追踪 Agent
- 对接物流公司API
- 实时追踪包裹
- 异常告警

### 22. 财务审计 Agent
- 核对采购/销售数据
- 生成财务报表
- 利润分析

### 23. 供应商评估 Agent
- 评估供应商表现
- 计算合作评分
- 推荐优质供应商

### 24. 数据报表总管 Agent
- 汇总所有数据
- 生成可视化报表
- AI分析建议

---

## Agent通用能力

所有Agent都具备:

1. **双模式运行**
   - 自主模式: Cron定时触发
   - 响应模式: Webhook接收任务

2. **记忆能力**
   - 短期记忆: Redis (会话状态)
   - 长期记忆: PostgreSQL (历史数据)
   - 向量记忆: Qdrant (语义检索)

3. **工具调用**
   - LangChain Tool框架
   - 支持自定义工具
   - 错误重试机制

4. **状态上报**
   - 实时上报到OpenClaw Dashboard
   - 记录日志到文件
   - 异常告警

5. **协作能力**
   - Redis Pub/Sub通信
   - 任务委托机制
   - 结果共享
