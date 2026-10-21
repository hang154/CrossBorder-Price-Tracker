(async () => {
  const root = document.querySelector('#sdpReview');
  if (!root) return {error: /access denied|captcha|접근.*제한|보안 확인/i.test(document.body.innerText) ? 'access_restricted' : 'review_root_missing'};
  const article = root.querySelector('article');
  let fiber = article && article[Object.keys(article).find(k => k.startsWith('__reactFiber'))];
  let data, params, querying;
  for (let i=0; fiber && i<18; i++, fiber=fiber.return) {
    const p = fiber.memoizedProps || {};
    if (p.reviews?.paging && p.searchParams) {data=p.reviews; params=p.searchParams; querying=p.querying; break;}
  }
  if (!data) return {error:'public_review_component_not_found', article_count:root.querySelectorAll('article').length};
  // Read only already-rendered review data; never return account state, names or emails.
  const hash = async value => [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value)))].map(b=>b.toString(16).padStart(2,'0')).join('');
  const product = location.pathname.match(/\/vp\/products\/(\d+)/)?.[1];
  const records = [];
  for (const r of data.paging.contents || []) {
    const m=r.member || {};
    const stable=m.memberId || m.id || r.reviewerId;
    const signature=stable ? 'id:'+stable : m.email ? 'masked:'+m.email+'|'+(m.name||'') : null;
    records.push({review_id:String(r.reviewId),product_id:String(r.productId),
      item_id:r.itemId == null ? null : String(r.itemId),
      vendor_item_id:r.vendorItemId == null ? null : String(r.vendorItemId),
      item_name:typeof r.itemName === 'string' ? r.itemName : null,
      vendor_name:typeof r.vendorName === 'string' ? r.vendorName : null,
      reviewer_key:signature ? await hash(product+'|'+signature) : null,
      identity_basis:stable ? 'stable_public_id' : signature ? 'masked_signature' : 'unknown',
      review_at:r.reviewAt,created_at:r.createdAt,rating:r.rating,
      has_text:!!((r.title||'').trim() || (r.content||'').trim()),
      has_media:!!(r.attachments?.length || r.videoAttachments?.length)});
  }
  const paging=data.paging;
  return {source_url:location.href,product_id:product,title:document.title,querying:!!querying,
    source:'rendered_public_review_component',sort:params.sortBy,filters:{q:params.q,ratings:params.ratings,market:params.market},
    page:Number(paging.currentPage || paging.page),total_pages:Number(paging.totalPage),
    listed_review_count:Number(paging.totalCount),rating_count:data.ratingSummaryTotal?.ratingCount ?? null,
    records};
})()
