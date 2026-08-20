/**
 * 发布配置 4 级优先级合并（spec §3.3）
 * accountOv > platformOv > platformDefault > common
 * 纯函数：不依赖组件状态，可单测。
 */

/**
 * 解析定时发布时间:账号级优先,且账号级显式设置(含清空)就以账号级为准。
 *
 * 关键: accountOv.scheduleTime === null 表示用户在账号级"清空了定时"(=不定时),
 * 不能用 ?? fallback 到平台级默认 —— 否则平台级的定时时间会强制定时该账号。
 * 仅当账号 override 完全没带 scheduleTime key(未操作过)时,才 fallback 到平台级。
 */
function _resolveScheduleTime(accountOv: Record<string,any> | undefined, platformOv: Record<string,any> | undefined, platformDefault: Record<string,any> | undefined) {
  if (accountOv && Object.prototype.hasOwnProperty.call(accountOv, 'scheduleTime')) {
    // 账号级显式设置过(含 null/'') → 以账号级为准(null/'' = 不定时)
    return accountOv.scheduleTime || ''
  }
  if (platformOv && Object.prototype.hasOwnProperty.call(platformOv, 'scheduleTime')) {
    return platformOv.scheduleTime || ''
  }
  return platformDefault?.scheduleTime || ''
}

function mergeConfig(common: Record<string,any>, platformDefault: Record<string,any> | undefined, platformOv: Record<string,any> | undefined, accountOv: Record<string,any> | undefined) {
  return {
    // 文本字段 4 级合并（账号 > 渠道 > 平台默认），与视频/封面/平台特有字段一致
    title: accountOv?.title ?? platformOv?.title ?? platformDefault?.title ?? '',
    description: accountOv?.description ?? platformOv?.description ?? platformDefault?.description ?? '',
    tags: accountOv?.tags ?? platformOv?.tags ?? platformDefault?.tags ?? [],
    // 视频/封面走 4 级合并 → commonConfig 兜底
    coverLandscape: accountOv?.coverLandscape ?? platformOv?.coverLandscape ?? common.coverLandscape,
    coverPortrait:  accountOv?.coverPortrait  ?? platformOv?.coverPortrait  ?? common.coverPortrait,
    coverLandscape169: accountOv?.coverLandscape169 ?? platformOv?.coverLandscape169 ?? common.coverLandscape169,
    coverPortrait916:  accountOv?.coverPortrait916  ?? platformOv?.coverPortrait916  ?? common.coverPortrait916,
    videoLandscape: accountOv?.videoLandscape ?? platformOv?.videoLandscape ?? common.videoLandscape,
    videoPortrait:  accountOv?.videoPortrait  ?? platformOv?.videoPortrait  ?? common.videoPortrait,
    // 平台特有字段走 platformDefault 兜底
    enableTimer: accountOv?.enableTimer ?? platformOv?.enableTimer ?? platformDefault?.enableTimer ?? 0,
    // scheduleTime: 账号级若已显式设置(含清空为 null/'')就以账号级为准,不 fallback
    // 到平台级默认 —— 否则平台级的定时时间会污染"账号没设定时"的账号(实测 bug)。
    // 用 _hasOwn 判断:账号 override 显式带过该 key 才采纳账号级值(含 null/空=不定时)。
    scheduleTime: _resolveScheduleTime(accountOv, platformOv, platformDefault),
    aiContent: accountOv?.aiContent ?? platformOv?.aiContent ?? platformDefault?.aiContent ?? '',
    isOriginal: accountOv?.isOriginal ?? platformOv?.isOriginal ?? platformDefault?.isOriginal ?? false,
    // 平台特有字段：4 级合并（账号 > 渠道 > 平台默认），与视频/封面一致
    creationDeclaration: accountOv?.creationDeclaration ?? platformOv?.creationDeclaration ?? platformDefault?.creationDeclaration,
    // B 站转载来源(创作声明=转载 时必填)
    biliRepostSource: accountOv?.biliRepostSource ?? platformOv?.biliRepostSource ?? platformDefault?.biliRepostSource ?? '',
    riskWarning: accountOv?.riskWarning ?? platformOv?.riskWarning ?? platformDefault?.riskWarning,
    enableCashActivity: accountOv?.enableCashActivity ?? platformOv?.enableCashActivity ?? platformDefault?.enableCashActivity,
    supplementaryDeclaration: accountOv?.supplementaryDeclaration ?? platformOv?.supplementaryDeclaration ?? platformDefault?.supplementaryDeclaration,
    audience: accountOv?.audience ?? platformOv?.audience ?? platformDefault?.audience,
    alteredContent: accountOv?.alteredContent ?? platformOv?.alteredContent ?? platformDefault?.alteredContent,
    // 修：zone 字段也走 4 级合并（B 站分区），账号级填的 zone 才能进 publishData
    zone: accountOv?.zone ?? platformOv?.zone ?? platformDefault?.zone ?? '',
    // 知乎「所属领域」4 级合并
    category: accountOv?.category ?? platformOv?.category ?? platformDefault?.category ?? '',
    // 平台特有字段 4 级合并（账号 > 渠道 > 平台默认）—— 补回漏的
    // 抖音
    activityId: accountOv?.activityId ?? platformOv?.activityId ?? platformDefault?.activityId ?? [],
    hotspotId: accountOv?.hotspotId ?? platformOv?.hotspotId ?? platformDefault?.hotspotId ?? '',
    hotspotData: accountOv?.hotspotData ?? platformOv?.hotspotData ?? platformDefault?.hotspotData ?? null,
    selectedTag: accountOv?.selectedTag ?? platformOv?.selectedTag ?? platformDefault?.selectedTag ?? null,
    tagType: accountOv?.tagType ?? platformOv?.tagType ?? platformDefault?.tagType ?? '',
    tagValue: accountOv?.tagValue ?? platformOv?.tagValue ?? platformDefault?.tagValue ?? '',
    mixId: accountOv?.mixId ?? platformOv?.mixId ?? platformDefault?.mixId ?? '',
    mixData: accountOv?.mixData ?? platformOv?.mixData ?? platformDefault?.mixData ?? null,
    // B 站
    topic: accountOv?.topic ?? platformOv?.topic ?? platformDefault?.topic ?? '',
    // 视频号
    isDraft: accountOv?.isDraft ?? platformOv?.isDraft ?? platformDefault?.isDraft ?? false,
    location: accountOv?.location ?? platformOv?.location ?? platformDefault?.location ?? '',
    // 平台特有字段 4 级合并（账号 > 渠道 > 平台默认）—— 补回 xiaohongshu 漏的
    collection: accountOv?.collection ?? platformOv?.collection ?? platformDefault?.collection ?? '',
    groupChat: accountOv?.groupChat ?? platformOv?.groupChat ?? platformDefault?.groupChat ?? '',
    // 小红书合集(账号级配置)
    collectionId: accountOv?.collectionId ?? platformOv?.collectionId ?? platformDefault?.collectionId ?? '',
    collectionName: accountOv?.collectionName ?? platformOv?.collectionName ?? platformDefault?.collectionName ?? '',
    collectionData: accountOv?.collectionData ?? platformOv?.collectionData ?? platformDefault?.collectionData ?? null,
    // 小红书内容来源声明联动字段(平台级)
    xhsSourceType: accountOv?.xhsSourceType ?? platformOv?.xhsSourceType ?? platformDefault?.xhsSourceType ?? '',
    xhsShootLocation: accountOv?.xhsShootLocation ?? platformOv?.xhsShootLocation ?? platformDefault?.xhsShootLocation ?? '',
    xhsShootLocationData: accountOv?.xhsShootLocationData ?? platformOv?.xhsShootLocationData ?? platformDefault?.xhsShootLocationData ?? null,
    xhsShootDate: accountOv?.xhsShootDate ?? platformOv?.xhsShootDate ?? platformDefault?.xhsShootDate ?? '',
    xhsRepostSource: accountOv?.xhsRepostSource ?? platformOv?.xhsRepostSource ?? platformDefault?.xhsRepostSource ?? '',
    // 微博
    videoType: accountOv?.videoType ?? platformOv?.videoType ?? platformDefault?.videoType ?? '',
    weiboCategory: accountOv?.weiboCategory ?? platformOv?.weiboCategory ?? platformDefault?.weiboCategory ?? [],
    weiboCollectionName: accountOv?.weiboCollectionName ?? platformOv?.weiboCollectionName ?? platformDefault?.weiboCollectionName ?? '',
    contentStatement: accountOv?.contentStatement ?? platformOv?.contentStatement ?? platformDefault?.contentStatement ?? '',
    contentStatement2: accountOv?.contentStatement2 ?? platformOv?.contentStatement2 ?? platformDefault?.contentStatement2 ?? '',
    contentStatement2Optional: accountOv?.contentStatement2Optional ?? platformOv?.contentStatement2Optional ?? platformDefault?.contentStatement2Optional ?? '',
    // 支付宝
    authorStatement: accountOv?.authorStatement ?? platformOv?.authorStatement ?? platformDefault?.authorStatement ?? '',
    reprintUrl: accountOv?.reprintUrl ?? platformOv?.reprintUrl ?? platformDefault?.reprintUrl ?? '',
    compilation: accountOv?.compilation ?? platformOv?.compilation ?? platformDefault?.compilation ?? '',
    compilationData: accountOv?.compilationData ?? platformOv?.compilationData ?? platformDefault?.compilationData ?? null,
    // 今日头条
    enableGenerateImage: accountOv?.enableGenerateImage ?? platformOv?.enableGenerateImage ?? platformDefault?.enableGenerateImage ?? true,
    extendLink: accountOv?.extendLink ?? platformOv?.extendLink ?? platformDefault?.extendLink ?? false,
    extendLinkUrl: accountOv?.extendLinkUrl ?? platformOv?.extendLinkUrl ?? platformDefault?.extendLinkUrl ?? '',
    // B 站合集(账号级)
    biliCollectionName: accountOv?.biliCollectionName ?? platformOv?.biliCollectionName ?? platformDefault?.biliCollectionName ?? '',
    biliCollectionData: accountOv?.biliCollectionData ?? platformOv?.biliCollectionData ?? platformDefault?.biliCollectionData ?? null,
    // 视频号合集(账号级)
    channelsCollectionName: accountOv?.channelsCollectionName ?? platformOv?.channelsCollectionName ?? platformDefault?.channelsCollectionName ?? '',
    channelsCollectionData: accountOv?.channelsCollectionData ?? platformOv?.channelsCollectionData ?? platformDefault?.channelsCollectionData ?? null,
    // 视频号位置(账号级,空=不显示位置)
    channelsLocationName: accountOv?.channelsLocationName ?? platformOv?.channelsLocationName ?? platformDefault?.channelsLocationName ?? '',
    channelsLocationData: accountOv?.channelsLocationData ?? platformOv?.channelsLocationData ?? platformDefault?.channelsLocationData ?? null,
    // 视频号活动:虽然卡片按平台级显示,但 watch(form) 把值回写到 accountOverrides
    // (与合集/位置同模式),所以 4 级合并才能取到草稿恢复后的值
    channelsActivityName: accountOv?.channelsActivityName ?? platformOv?.channelsActivityName ?? platformDefault?.channelsActivityName ?? '',
    channelsActivityData: accountOv?.channelsActivityData ?? platformOv?.channelsActivityData ?? platformDefault?.channelsActivityData ?? null,
    // 视频号视频标注(平台级):所有选项(含「无需标注」)都会去页面真正选中
    channelsMarkTag: accountOv?.channelsMarkTag ?? platformOv?.channelsMarkTag ?? platformDefault?.channelsMarkTag ?? '无需标注',
    channelsShootDate: accountOv?.channelsShootDate ?? platformOv?.channelsShootDate ?? platformDefault?.channelsShootDate ?? '',
    channelsShootRegion: accountOv?.channelsShootRegion ?? platformOv?.channelsShootRegion ?? platformDefault?.channelsShootRegion ?? [],
    channelsRepostSource: accountOv?.channelsRepostSource ?? platformOv?.channelsRepostSource ?? platformDefault?.channelsRepostSource ?? '',
    // CSDN 是否推荐(平台级开关)
    recommend: accountOv?.recommend ?? platformOv?.recommend ?? platformDefault?.recommend ?? false,
    // VIVO 平台特有字段(平台级)
    vivoLocationName: accountOv?.vivoLocationName ?? platformOv?.vivoLocationName ?? platformDefault?.vivoLocationName ?? '',
    vivoLocationData: accountOv?.vivoLocationData ?? platformOv?.vivoLocationData ?? platformDefault?.vivoLocationData ?? null,
    vivoDistribution: accountOv?.vivoDistribution ?? platformOv?.vivoDistribution ?? platformDefault?.vivoDistribution ?? false,
    vivoDeclaration: accountOv?.vivoDeclaration ?? platformOv?.vivoDeclaration ?? platformDefault?.vivoDeclaration ?? '',
    vivoPrivacy: accountOv?.vivoPrivacy ?? platformOv?.vivoPrivacy ?? platformDefault?.vivoPrivacy ?? '公开',
    vivoDownloadPermission: accountOv?.vivoDownloadPermission ?? platformOv?.vivoDownloadPermission ?? platformDefault?.vivoDownloadPermission ?? '允许',
    // 微信公众号合集(账号级)
    gzhCollectionName: accountOv?.gzhCollectionName ?? platformOv?.gzhCollectionName ?? platformDefault?.gzhCollectionName ?? '',
    gzhCollectionData: accountOv?.gzhCollectionData ?? platformOv?.gzhCollectionData ?? platformDefault?.gzhCollectionData ?? null,
    // 微信公众号创作来源(平台级)
    gzhClaimSource: accountOv?.gzhClaimSource ?? platformOv?.gzhClaimSource ?? platformDefault?.gzhClaimSource ?? '',
    // 淘宝光合创作者声明(平台级)
    guangheClaim: accountOv?.guangheClaim ?? platformOv?.guangheClaim ?? platformDefault?.guangheClaim ?? '',
    // 淘宝光合关联商品/店铺(平台级, radio 互斥, 名称列表最多 6 个)
    guangheLinkType: accountOv?.guangheLinkType ?? platformOv?.guangheLinkType ?? platformDefault?.guangheLinkType ?? '',
    guangheProducts: accountOv?.guangheProducts ?? platformOv?.guangheProducts ?? platformDefault?.guangheProducts ?? [],
    guangheShops: accountOv?.guangheShops ?? platformOv?.guangheShops ?? platformDefault?.guangheShops ?? [],
    // 京东关联挂件(平台级, radio 互斥)
    jdRelatedType: accountOv?.jdRelatedType ?? platformOv?.jdRelatedType ?? platformDefault?.jdRelatedType ?? '',
    jdProducts: accountOv?.jdProducts ?? platformOv?.jdProducts ?? platformDefault?.jdProducts ?? [],
    jdNovel: accountOv?.jdNovel ?? platformOv?.jdNovel ?? platformDefault?.jdNovel ?? '',
    jdNovelData: accountOv?.jdNovelData ?? platformOv?.jdNovelData ?? platformDefault?.jdNovelData ?? null,
    jdDeclaration: accountOv?.jdDeclaration ?? platformOv?.jdDeclaration ?? platformDefault?.jdDeclaration ?? '',
  }
}

export { mergeConfig }
