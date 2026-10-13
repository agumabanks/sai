import aiomysql
from typing import Dict, Any, List, Optional
from core.config import get_settings
from core.skills.base import BaseSkill, SkillResult


def _soko_db_config() -> dict:
    s = get_settings()
    return {
        "host": s.soko_db_host,
        "port": s.soko_db_port,
        "user": s.soko_db_user,
        "password": s.soko_db_password,
        "db": s.soko_db_name,
        "autocommit": True,
    }


def _admin_base() -> str:
    s = get_settings()
    return f"{s.soko_site_url.rstrip('/')}{s.soko_admin_path}"


def admin_links() -> dict:
    base = _admin_base()
    site = get_settings().soko_site_url.rstrip("/")
    return {
        "dashboard": f"{base}",
        "all_orders": f"{base}/all_orders",
        "unpaid_orders": f"{base}/unpaid_orders",
        "seller_orders": f"{base}/seller_orders",
        "sellers": f"{base}/sellers",
        "products_all": f"{base}/products/all",
        "products_admin": f"{base}/products/admin",
        "customers": f"{base}/customers",
        "categories": f"{base}/categories",
        "crm_contacts": f"{base}/crm/contacts",
        "soko_studio": f"{base}/soko-studio",
        "storefront": site,
        "seller_os": f"{site}/seller/os",
        "seller_login": f"{site}/seller/login",
        "customer_dashboard": f"{site}/dashboard",
        "admin_login": f"{site}/admin/login",
    }


def platform_surfaces() -> dict:
    links = admin_links()
    site = get_settings().soko_site_url.rstrip("/")
    return {
        "command": {
            "id": "command",
            "label": "Command",
            "description": "Analytics, orders, alerts, and ops",
            "type": "native",
            "icon": "chart",
            "roles": ["admin", "operator"],
        },
        "admin": {
            "id": "admin",
            "label": "Admin",
            "description": "Full Laravel platform administration",
            "type": "embed",
            "url": links["dashboard"],
            "open_url": links["dashboard"],
            "login_url": links["admin_login"],
            "icon": "shield",
            "roles": ["admin", "operator"],
        },
        "seller": {
            "id": "seller",
            "label": "Seller OS",
            "description": "Seller business operating system",
            "type": "embed",
            "url": links["seller_os"],
            "open_url": links["seller_os"],
            "login_url": links["seller_login"],
            "icon": "store",
            "roles": ["admin", "operator", "seller"],
        },
        "store": {
            "id": "store",
            "label": "Store",
            "description": "Customer marketplace storefront",
            "type": "embed",
            "url": links["storefront"],
            "open_url": links["storefront"],
            "icon": "cart",
            "roles": ["admin", "operator", "customer"],
        },
        "customers": {
            "id": "customers",
            "label": "Buyers",
            "description": "Registered marketplace customers",
            "type": "native",
            "admin_url": links["customers"],
            "icon": "users",
            "roles": ["admin", "operator"],
        },
    }


class SokoAgentDetail(BaseSkill):
    async def execute(self, params: Dict[str, Any], context: Any) -> SkillResult:
        action = params.get("action", "platform_health")
        limit = int(params.get("limit", 20) or 20)
        limit = max(1, min(limit, 100))

        try:
            pool = await aiomysql.create_pool(**_soko_db_config())

            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    if action == "order_metrics":
                        return await self._get_order_metrics(cur)
                    if action == "distressed_sellers":
                        return await self._get_distressed_sellers(cur, limit)
                    if action == "platform_health":
                        return await self._get_platform_health(cur)
                    if action == "recent_orders":
                        return await self._get_recent_orders(cur, params, limit)
                    if action == "list_sellers":
                        return await self._get_list_sellers(cur, params, limit)
                    if action == "product_queue":
                        return await self._get_product_queue(cur, params, limit)
                    if action == "admin_alerts":
                        return await self._get_admin_alerts(cur)
                    if action == "dashboard":
                        return await self._get_dashboard(cur, limit)
                    if action == "list_customers":
                        return await self._get_list_customers(cur, params, limit)
                    if action == "platform_surfaces":
                        return await self._get_platform_surfaces(cur)
                    if action == "pulse":
                        return await self._get_pulse(cur, limit)
                    if action == "verify_seller":
                        seller_id = int(params.get("seller_id") or 0)
                        if seller_id < 1:
                            return SkillResult(success=False, error="seller_id required")
                        return await self._verify_seller(cur, conn, seller_id)
                    if action == "approve_product":
                        product_id = int(params.get("product_id") or 0)
                        if product_id < 1:
                            return SkillResult(success=False, error="product_id required")
                        return await self._approve_product(cur, conn, product_id)
                    return SkillResult(success=False, error=f"Unknown action: {action}")

        except Exception as e:
            return SkillResult(success=False, error=f"Soko DB Connection/Query Error: {str(e)}")
        finally:
            if "pool" in locals():
                pool.close()
                await pool.wait_closed()

    async def _get_order_metrics(self, cur) -> SkillResult:
        await cur.execute(
            "SELECT payment_status, delivery_status, COUNT(*) as count "
            "FROM orders WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY) "
            "GROUP BY payment_status, delivery_status"
        )
        recent_orders = await cur.fetchall()

        await cur.execute(
            "SELECT SUM(grand_total) as revenue FROM orders "
            "WHERE created_at >= DATE_SUB(NOW(), INTERVAL 1 DAY) AND payment_status = 'paid'"
        )
        daily_revenue = await cur.fetchone()

        rev = float(daily_revenue["revenue"] or 0)
        output = "🛒 Soko Recent Order Metrics (Last 7 Days):\n"
        for row in recent_orders:
            output += (
                f"- Payment: {row['payment_status'] or 'N/A'}, "
                f"Delivery: {row['delivery_status'] or 'N/A'} -> {row['count']} orders\n"
            )
        output += f"\n💰 Daily Revenue (Last 24h, Paid): {rev:,.2f}"

        return SkillResult(
            success=True,
            output=output,
            data={"recent_orders": recent_orders, "daily_revenue": rev},
        )

    async def _get_distressed_sellers(self, cur, limit: int) -> SkillResult:
        await cur.execute(
            """
            SELECT s.id as seller_id, u.name as shop_name, u.phone, COUNT(o.id) as pending_orders
            FROM sellers s
            JOIN users u ON s.user_id = u.id
            JOIN orders o ON o.seller_id = s.user_id
            WHERE o.delivery_status = 'pending' AND o.created_at < DATE_SUB(NOW(), INTERVAL 2 DAY)
            GROUP BY s.id, u.name, u.phone
            ORDER BY pending_orders DESC
            LIMIT %s
            """,
            (limit,),
        )
        sellers = await cur.fetchall()

        if not sellers:
            return SkillResult(
                success=True,
                output="✅ No distressed sellers found (no badly delayed orders).",
                data={"sellers": []},
            )

        output = f"⚠️ Distressed Soko Sellers ({len(sellers)} found with delayed orders > 48h):\n"
        for s in sellers:
            output += f"- {s['shop_name']} (Phone: {s['phone']}): {s['pending_orders']} delayed orders\n"

        return SkillResult(success=True, output=output, data={"sellers": sellers})

    async def _get_platform_health(self, cur) -> SkillResult:
        await cur.execute("SELECT COUNT(*) as sellers FROM sellers WHERE verification_status = 1")
        active_sellers = await cur.fetchone()

        await cur.execute("SELECT COUNT(*) as products FROM products WHERE published = 1 AND deleted_at IS NULL")
        active_products = await cur.fetchone()

        await cur.execute("SELECT COUNT(*) as users FROM users")
        total_users = await cur.fetchone()

        await cur.execute("SELECT COUNT(*) as pending FROM sellers WHERE verification_status = 0")
        pending_sellers = await cur.fetchone()

        await cur.execute(
            "SELECT COUNT(*) as queue FROM products WHERE deleted_at IS NULL AND (published = 0 OR approved = 0)"
        )
        product_queue = await cur.fetchone()

        output = (
            "📊 Soko Platform Health:\n"
            f"- Active Verified Sellers: {active_sellers['sellers']}\n"
            f"- Published Products: {active_products['products']}\n"
            f"- Total Users: {total_users['users']}\n"
            f"- Pending Seller Verifications: {pending_sellers['pending']}\n"
            f"- Products Needing Review: {product_queue['queue']}"
        )
        return SkillResult(
            success=True,
            output=output,
            data={
                "active_sellers": active_sellers["sellers"],
                "active_products": active_products["products"],
                "total_users": total_users["users"],
                "pending_sellers": pending_sellers["pending"],
                "product_queue": product_queue["queue"],
            },
        )

    async def _get_recent_orders(self, cur, params: dict, limit: int) -> SkillResult:
        clauses = ["1=1"]
        args: List[Any] = []

        payment = params.get("payment_status") or params.get("payment")
        if payment:
            clauses.append("o.payment_status = %s")
            args.append(payment)

        delivery = params.get("delivery_status") or params.get("delivery")
        if delivery:
            clauses.append("o.delivery_status = %s")
            args.append(delivery)

        search = (params.get("search") or "").strip()
        if search:
            clauses.append("(o.code LIKE %s OR u.name LIKE %s OR u.email LIKE %s OR u.phone LIKE %s OR su.name LIKE %s)")
            like = f"%{search}%"
            args.extend([like, like, like, like, like])

        where = " AND ".join(clauses)
        args.append(limit)

        await cur.execute(
            f"""
            SELECT o.id, o.code, o.user_id, o.seller_id,
                   u.name AS buyer_name, u.email AS buyer_email, u.phone AS buyer_phone,
                   su.name AS seller_name,
                   o.grand_total, o.payment_status, o.delivery_status,
                   o.payment_type, o.created_at
            FROM orders o
            LEFT JOIN users u ON o.user_id = u.id
            LEFT JOIN users su ON o.seller_id = su.id
            WHERE {where}
            ORDER BY o.created_at DESC
            LIMIT %s
            """,
            tuple(args),
        )
        rows = await cur.fetchall()
        base = _admin_base()
        for row in rows:
            row["admin_url"] = f"{base}/all_orders/{row['id']}/show"
            row["grand_total"] = float(row["grand_total"] or 0)

        return SkillResult(success=True, output=f"Found {len(rows)} orders", data={"orders": rows})

    async def _get_list_sellers(self, cur, params: dict, limit: int) -> SkillResult:
        clauses = ["1=1"]
        args: List[Any] = []

        verification = params.get("verification")
        if verification is not None and verification != "":
            clauses.append("s.verification_status = %s")
            args.append(int(verification))

        search = (params.get("search") or "").strip()
        if search:
            clauses.append("(u.name LIKE %s OR u.phone LIKE %s OR u.email LIKE %s)")
            like = f"%{search}%"
            args.extend([like, like, like])

        where = " AND ".join(clauses)
        args.append(limit)

        await cur.execute(
            f"""
            SELECT s.id, s.user_id, u.name AS shop_name, u.phone, u.email,
                   s.verification_status, s.num_of_sale, s.rating, s.created_at
            FROM sellers s
            JOIN users u ON s.user_id = u.id
            WHERE {where}
            ORDER BY s.created_at DESC
            LIMIT %s
            """,
            tuple(args),
        )
        rows = await cur.fetchall()
        base = _admin_base()
        for row in rows:
            verified = int(row.get("verification_status") or 0) == 1
            row["status"] = "verified" if verified else "pending"
            row["admin_url"] = f"{base}/sellers"
            row["verify_url"] = f"{base}/sellers/view/{row['id']}/verification"
            row["impersonate_url"] = f"{base}/sellers/login/{row['id']}"
            row["seller_os_url"] = f"{get_settings().soko_site_url.rstrip('/')}/seller/os"
            row["rating"] = float(row.get("rating") or 0)

        return SkillResult(success=True, output=f"Found {len(rows)} sellers", data={"sellers": rows})

    async def _get_product_queue(self, cur, params: dict, limit: int) -> SkillResult:
        clauses = ["p.deleted_at IS NULL", "(p.published = 0 OR p.approved = 0)"]
        args: List[Any] = []
        search = (params.get("search") or "").strip()
        if search:
            clauses.append("(p.name LIKE %s OR u.name LIKE %s)")
            like = f"%{search}%"
            args.extend([like, like])
        where = " AND ".join(clauses)
        args.append(limit)
        await cur.execute(
            f"""
            SELECT p.id, p.name, p.user_id, u.name AS seller_name,
                   p.published, p.approved, p.current_stock,
                   p.unit_price, p.num_of_sale, p.updated_at
            FROM products p
            LEFT JOIN users u ON p.user_id = u.id
            WHERE {where}
            ORDER BY p.updated_at DESC
            LIMIT %s
            """,
            tuple(args),
        )
        rows = await cur.fetchall()
        base = _admin_base()
        for row in rows:
            row["unit_price"] = float(row.get("unit_price") or 0)
            row["admin_url"] = f"{base}/products/seller/{row['id']}/edit"
            issues = []
            if not int(row.get("published") or 0):
                issues.append("unpublished")
            if not int(row.get("approved") or 0):
                issues.append("unapproved")
            row["issues"] = issues

        return SkillResult(success=True, output=f"Found {len(rows)} products in queue", data={"products": rows})

    async def _get_admin_alerts(self, cur) -> SkillResult:
        alerts = []

        await cur.execute("SELECT COUNT(*) AS c FROM sellers WHERE verification_status = 0")
        pending_sellers = (await cur.fetchone())["c"]
        if pending_sellers:
            alerts.append({
                "id": "pending_sellers",
                "severity": "warning",
                "label": "Seller verifications pending",
                "count": pending_sellers,
                "url": f"{_admin_base()}/sellers",
            })

        await cur.execute(
            "SELECT COUNT(*) AS c FROM products WHERE deleted_at IS NULL AND (published = 0 OR approved = 0)"
        )
        product_queue = (await cur.fetchone())["c"]
        if product_queue:
            alerts.append({
                "id": "product_queue",
                "severity": "warning",
                "label": "Products need review",
                "count": product_queue,
                "url": f"{_admin_base()}/products/all",
            })

        await cur.execute(
            "SELECT COUNT(*) AS c FROM orders WHERE payment_status = 'unpaid' AND delivery_status = 'pending'"
        )
        unpaid_pending = (await cur.fetchone())["c"]
        if unpaid_pending:
            alerts.append({
                "id": "unpaid_pending",
                "severity": "critical",
                "label": "Unpaid pending orders",
                "count": unpaid_pending,
                "url": f"{_admin_base()}/unpaid_orders",
            })

        await cur.execute(
            """
            SELECT COUNT(DISTINCT s.id) AS c
            FROM sellers s
            JOIN orders o ON o.seller_id = s.user_id
            WHERE o.delivery_status = 'pending' AND o.created_at < DATE_SUB(NOW(), INTERVAL 2 DAY)
            """
        )
        distressed = (await cur.fetchone())["c"]
        if distressed:
            alerts.append({
                "id": "distressed_sellers",
                "severity": "critical",
                "label": "Distressed sellers (>48h)",
                "count": distressed,
                "url": f"{_admin_base()}/seller_orders",
                "action": "tab:distressed",
            })

        return SkillResult(success=True, output=f"{len(alerts)} alerts", data={"alerts": alerts})

    async def _get_dashboard(self, cur, limit: int) -> SkillResult:
        health = await self._get_platform_health(cur)
        metrics = await self._get_order_metrics(cur)
        alerts = await self._get_admin_alerts(cur)
        distressed = await self._get_distressed_sellers(cur, min(limit, 10))
        orders = await self._get_recent_orders(cur, {}, min(limit, 15))
        pending_sellers = await self._get_list_sellers(cur, {"verification": 0}, min(limit, 10))

        health_data = health.data or {}
        metrics_data = metrics.data or {}
        recent = metrics_data.get("recent_orders") or []
        total_orders_7d = sum(int(r.get("count") or 0) for r in recent)

        return SkillResult(
            success=True,
            output="Soko dashboard loaded",
            data={
                "health": health_data,
                "metrics": metrics_data,
                "summary": {
                    "active_sellers": health_data.get("active_sellers", 0),
                    "active_products": health_data.get("active_products", 0),
                    "total_users": health_data.get("total_users", 0),
                    "pending_sellers": health_data.get("pending_sellers", 0),
                    "product_queue": health_data.get("product_queue", 0),
                    "total_orders_7d": total_orders_7d,
                    "daily_revenue": metrics_data.get("daily_revenue", 0),
                    "distressed_count": len((distressed.data or {}).get("sellers") or []),
                },
                "alerts": (alerts.data or {}).get("alerts") or [],
                "recent_orders": (orders.data or {}).get("orders") or [],
                "pending_sellers": (pending_sellers.data or {}).get("sellers") or [],
                "distressed_sellers": (distressed.data or {}).get("sellers") or [],
                "admin_links": admin_links(),
                "surfaces": platform_surfaces(),
            },
        )

    async def _verify_seller(self, cur, conn, seller_id: int) -> SkillResult:
        await cur.execute("SELECT id, verification_status FROM sellers WHERE id = %s", (seller_id,))
        row = await cur.fetchone()
        if not row:
            return SkillResult(success=False, error=f"Seller {seller_id} not found")
        if int(row.get("verification_status") or 0) == 1:
            return SkillResult(success=True, output="Already verified", data={"seller_id": seller_id, "status": "verified"})
        await cur.execute("UPDATE sellers SET verification_status = 1 WHERE id = %s", (seller_id,))
        await conn.commit()
        return SkillResult(success=True, output=f"Seller {seller_id} verified", data={"seller_id": seller_id, "status": "verified"})

    async def _approve_product(self, cur, conn, product_id: int) -> SkillResult:
        await cur.execute(
            "SELECT id, name, approved, published, deleted_at FROM products WHERE id = %s",
            (product_id,),
        )
        row = await cur.fetchone()
        if not row:
            return SkillResult(success=False, error=f"Product {product_id} not found")
        if row.get("deleted_at"):
            return SkillResult(success=False, error=f"Product {product_id} is deleted")
        if int(row.get("approved") or 0) == 1:
            return SkillResult(
                success=True,
                output="Already approved",
                data={"product_id": product_id, "status": "approved", "name": row.get("name")},
            )
        await cur.execute("UPDATE products SET approved = 1 WHERE id = %s", (product_id,))
        await conn.commit()
        return SkillResult(
            success=True,
            output=f"Product {product_id} approved",
            data={"product_id": product_id, "status": "approved", "name": row.get("name")},
        )

    async def _get_pulse(self, cur, limit: int) -> SkillResult:
        health = await self._get_platform_health(cur)
        metrics = await self._get_order_metrics(cur)
        alerts = await self._get_admin_alerts(cur)
        distressed = await self._get_distressed_sellers(cur, min(limit, 8))
        orders = await self._get_recent_orders(cur, {}, min(limit, 8))

        health_data = health.data or {}
        metrics_data = metrics.data or {}
        alert_rows = (alerts.data or {}).get("alerts") or []
        distressed_rows = (distressed.data or {}).get("sellers") or []
        base = _admin_base()

        needs_you = []
        for a in alert_rows:
            needs_you.append({
                "id": a.get("id"),
                "severity": a.get("severity", "warning"),
                "title": a.get("label"),
                "subtitle": f"{a.get('count', 0)} items need attention",
                "count": a.get("count", 0),
                "action": a.get("action") or ("tab:products" if a.get("id") == "product_queue" else "tab:sellers" if a.get("id") == "pending_sellers" else "tab:orders"),
                "admin_url": a.get("url"),
            })

        for s in distressed_rows[:5]:
            name = s.get("shop_name") or s.get("name") or "Seller"
            phone = s.get("phone") or ""
            needs_you.append({
                "id": f"distressed-{s.get('seller_id')}",
                "severity": "critical",
                "title": name,
                "subtitle": f"{s.get('pending_orders', 0)} orders delayed 48h+",
                "count": s.get("pending_orders", 0),
                "phone": phone,
                "seller_id": s.get("seller_id"),
                "action": "distressed",
                "admin_url": f"{base}/seller_orders",
            })

        badge = sum(int(a.get("count") or 0) for a in alert_rows if a.get("severity") == "critical")
        badge += sum(int(s.get("pending_orders") or 0) for s in distressed_rows[:3])

        return SkillResult(
            success=True,
            output="Soko pulse",
            data={
                "summary": {
                    "active_sellers": health_data.get("active_sellers", 0),
                    "active_products": health_data.get("active_products", 0),
                    "pending_sellers": health_data.get("pending_sellers", 0),
                    "product_queue": health_data.get("product_queue", 0),
                    "daily_revenue": metrics_data.get("daily_revenue", 0),
                    "distressed_count": len(distressed_rows),
                },
                "needs_you": needs_you,
                "recent_orders": (orders.data or {}).get("orders") or [],
                "badge": badge,
                "admin_links": admin_links(),
            },
        )

    async def _get_list_customers(self, cur, params: dict, limit: int) -> SkillResult:
        clauses = ["u.user_type = 'customer'"]
        args: List[Any] = []

        search = (params.get("search") or "").strip()
        if search:
            clauses.append("(u.name LIKE %s OR u.email LIKE %s OR u.phone LIKE %s)")
            like = f"%{search}%"
            args.extend([like, like, like])

        where = " AND ".join(clauses)
        args.append(limit)

        await cur.execute(
            f"""
            SELECT u.id, u.name, u.email, u.phone, u.banned, u.created_at,
                   (SELECT COUNT(*) FROM orders o WHERE o.user_id = u.id) AS order_count
            FROM users u
            WHERE {where}
            ORDER BY u.created_at DESC
            LIMIT %s
            """,
            tuple(args),
        )
        rows = await cur.fetchall()
        base = _admin_base()
        for row in rows:
            row["admin_url"] = f"{base}/customers/login/{row['id']}"
            row["status"] = "banned" if int(row.get("banned") or 0) else "active"

        return SkillResult(success=True, output=f"Found {len(rows)} customers", data={"customers": rows})

    async def _get_platform_surfaces(self, cur) -> SkillResult:
        await cur.execute("SELECT COUNT(*) AS c FROM users WHERE user_type = 'customer'")
        customers = (await cur.fetchone())["c"]
        await cur.execute("SELECT COUNT(*) AS c FROM users WHERE user_type = 'seller'")
        sellers = (await cur.fetchone())["c"]
        await cur.execute("SELECT COUNT(*) AS c FROM sellers WHERE verification_status = 1")
        verified_sellers = (await cur.fetchone())["c"]

        return SkillResult(
            success=True,
            output="Soko platform surfaces",
            data={
                "surfaces": platform_surfaces(),
                "admin_links": admin_links(),
                "counts": {
                    "customers": customers,
                    "sellers": sellers,
                    "verified_sellers": verified_sellers,
                },
            },
        )


handler = SokoAgentDetail