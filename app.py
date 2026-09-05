from flask import Flask, jsonify, request, send_from_directory
import pandas as pd
import os

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
FRONTEND_DIR = os.path.join(BASE_DIR, "src")

PRODUCTS_FILE = os.path.join(DATA_DIR, "products.csv")
SALES_FILE = os.path.join(DATA_DIR, "sales.csv")


# =========================================================
# LOAD DATA
# =========================================================

def load_data():
    products = pd.read_csv(PRODUCTS_FILE)
    sales = pd.read_csv(SALES_FILE)

    sales["Date"] = pd.to_datetime(sales["Date"])

    products["Stock"] = pd.to_numeric(
        products["Stock"], errors="coerce"
    ).fillna(0)

    products["Price"] = pd.to_numeric(
        products["Price"], errors="coerce"
    ).fillna(0)

    sales["Quantity"] = pd.to_numeric(
        sales["Quantity"], errors="coerce"
    ).fillna(0)

    sales["Revenue"] = pd.to_numeric(
        sales["Revenue"], errors="coerce"
    ).fillna(0)

    return products, sales


products, sales = load_data()


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():
    response = send_from_directory(
        FRONTEND_DIR,
        "index.html"
    )

    response.headers["Cache-Control"] = (
        "no-store, no-cache, must-revalidate, max-age=0"
    )

    return response


# =========================================================
# PRODUCTS API
# =========================================================

@app.route("/api/products")
def get_products():
    return jsonify(
        products.to_dict(orient="records")
    )


# =========================================================
# SALES API
# =========================================================

@app.route("/api/sales")
def get_sales():

    result = sales.copy()

    result["Date"] = result["Date"].dt.strftime(
        "%Y-%m-%d"
    )

    return jsonify(
        result.to_dict(orient="records")
    )


# =========================================================
# DAILY INVENTORY ALERTS
# =========================================================

def generate_inventory_alerts():

    alerts = []

    # Calculate average daily sales
    start_date = sales["Date"].min()
    end_date = sales["Date"].max()

    total_days = (
        end_date - start_date
    ).days + 1

    if total_days <= 0:
        total_days = 1

    daily_sales = (
        sales.groupby("Product_ID")["Quantity"]
        .sum()
        / total_days
    )

    for _, product in products.iterrows():

        product_id = product["Product_ID"]
        product_name = product["Product_Name"]
        store = product["Store"]
        stock = float(product["Stock"])

        avg_daily_sales = float(
            daily_sales.get(product_id, 0)
        )

        # ---------------------------------------------
        # CRITICAL
        # ---------------------------------------------

        if stock <= 5:

            alerts.append({
                "product": product_name,
                "store": store,
                "stock": int(stock),
                "average_daily_sales": round(
                    avg_daily_sales, 2
                ),
                "status": "CRITICAL",
                "reason": (
                    f"Only {int(stock)} units are currently "
                    "available."
                ),
                "action": (
                    "Reorder immediately to avoid stock-out."
                )
            })

        # ---------------------------------------------
        # REORDER SOON
        # ---------------------------------------------

        elif stock <= 10:

            alerts.append({
                "product": product_name,
                "store": store,
                "stock": int(stock),
                "average_daily_sales": round(
                    avg_daily_sales, 2
                ),
                "status": "REORDER SOON",
                "reason": (
                    f"Stock is {int(stock)} units, "
                    "which is below the 10-unit monitoring threshold."
                ),
                "action": (
                    "Plan replenishment soon."
                )
            })

        # ---------------------------------------------
        # FAST SELLING / INVENTORY RISK
        # ---------------------------------------------

        elif avg_daily_sales > 0:

            days_remaining = (
                stock / avg_daily_sales
            )

            if days_remaining <= 7:

                alerts.append({
                    "product": product_name,
                    "store": store,
                    "stock": int(stock),
                    "average_daily_sales": round(
                        avg_daily_sales, 2
                    ),
                    "estimated_days_remaining": round(
                        days_remaining, 1
                    ),
                    "status": "STOCK-OUT RISK",
                    "reason": (
                        f"At the current sales rate, "
                        f"approximately {days_remaining:.1f} "
                        "days of stock remain."
                    ),
                    "action": (
                        "Prioritize replenishment and monitor sales velocity."
                    )
                })

        # ---------------------------------------------
        # OVERSTOCK
        # ---------------------------------------------

        if stock > 30:

            alerts.append({
                "product": product_name,
                "store": store,
                "stock": int(stock),
                "average_daily_sales": round(
                    avg_daily_sales, 2
                ),
                "status": "OVERSTOCK",
                "reason": (
                    f"{int(stock)} units are currently in stock, "
                    "above the 30-unit overstock threshold."
                ),
                "action": (
                    "Consider promotions or reduce future purchases."
                )
            })

    return alerts


# =========================================================
# SUMMARY API
# =========================================================

@app.route("/api/summary")
def summary():

    total_revenue = float(
        sales["Revenue"].sum()
    )

    units_sold = int(
        sales["Quantity"].sum()
    )

    product_count = int(
        products["Product_ID"].nunique()
    )

    low_stock_count = int(
        (products["Stock"] <= 10).sum()
    )

    top_products = (
        sales.groupby("Product_Name")["Quantity"]
        .sum()
        .sort_values(ascending=False)
        .head(5)
    )

    top_selling = [
        {
            "product": name,
            "units": int(quantity)
        }
        for name, quantity in top_products.items()
    ]

    low_stock_products = products[
        products["Stock"] <= 10
    ]

    alerts = [
        {
            "product": row["Product_Name"],
            "stock": int(row["Stock"]),
            "store": row["Store"]
        }
        for _, row in low_stock_products.iterrows()
    ]

    inventory_alerts = generate_inventory_alerts()

    return jsonify({
        "total_revenue": total_revenue,
        "units_sold": units_sold,
        "product_count": product_count,
        "low_stock_count": low_stock_count,
        "top_selling": top_selling,
        "low_stock_products": alerts,
        "inventory_alerts": inventory_alerts
    })


# =========================================================
# STOCK-OUT PREDICTION
# =========================================================

def stock_out_prediction():

    if sales.empty:

        return [], (
            "Sales data is not available, so stock-out "
            "prediction cannot be calculated."
        )

    start_date = sales["Date"].min()
    end_date = sales["Date"].max()

    number_of_days = (
        end_date - start_date
    ).days + 1

    if number_of_days <= 0:
        number_of_days = 1

    sales_velocity = (
        sales.groupby("Product_ID")["Quantity"]
        .sum()
        / number_of_days
    )

    results = []

    for _, product in products.iterrows():

        product_id = product["Product_ID"]
        product_name = product["Product_Name"]
        current_stock = float(product["Stock"])

        average_daily_sales = float(
            sales_velocity.get(product_id, 0)
        )

        if average_daily_sales <= 0:
            continue

        days_remaining = (
            current_stock / average_daily_sales
        )

        results.append({
            "Product_ID": product_id,
            "Product_Name": product_name,
            "Store": product["Store"],
            "Current_Stock": int(current_stock),
            "Average_Daily_Sales": round(
                average_daily_sales, 2
            ),
            "Estimated_Days_Remaining": round(
                days_remaining, 1
            )
        })

    results.sort(
        key=lambda x:
        x["Estimated_Days_Remaining"]
    )

    return results, None


# =========================================================
# CHAT API
# =========================================================

@app.route("/api/chat", methods=["POST"])
def chat():

    data = request.get_json(
        silent=True
    ) or {}

    question = str(
        data.get("question", "")
    ).strip()

    if not question:

        return jsonify({
            "answer": "Please enter a question.",
            "evidence": {},
            "recommendation": ""
        })

    q = question.lower()


    # =====================================================
    # TOTAL REVENUE
    # =====================================================

    if (
        "total revenue" in q
        or (
            "revenue" in q
            and "total" in q
        )
        or "sales revenue" in q
    ):

        total_revenue = float(
            sales["Revenue"].sum()
        )

        return jsonify({
            "answer":
                f"Total revenue is ₹{total_revenue:,.0f}.",

            "evidence": {
                "total_revenue": total_revenue,
                "source": "sales.csv"
            },

            "recommendation":
                "Continue monitoring revenue trends by product and store."
        })


    # =====================================================
    # LOW STOCK
    # =====================================================

    if (
        "low stock" in q
        or "running out" in q
        or "low inventory" in q
        or "stock is low" in q
    ):

        low_stock = products[
            products["Stock"] <= 10
        ]

        if low_stock.empty:

            return jsonify({
                "answer":
                    "No products currently meet the "
                    "low-stock threshold of 10 units or less.",

                "evidence": {
                    "threshold": 10
                },

                "recommendation":
                    "Continue monitoring inventory levels."
            })

        items = []

        for _, row in low_stock.iterrows():

            items.append(
                f'{row["Product_Name"]}: '
                f'{int(row["Stock"])} units'
            )

        return jsonify({
            "answer":
                "Low-stock products: "
                + ", ".join(items)
                + ".",

            "evidence": {
                "threshold": 10,

                "products": [
                    {
                        "product":
                            row["Product_Name"],

                        "stock":
                            int(row["Stock"]),

                        "store":
                            row["Store"]
                    }

                    for _, row
                    in low_stock.iterrows()
                ]
            },

            "recommendation":
                "Prioritize replenishment for these products "
                "before stock reaches zero."
        })


    # =====================================================
    # OVERSTOCK
    # =====================================================

    if (
        "overstock" in q
        or "over stocked" in q
        or "excess stock" in q
        or "too much stock" in q
    ):

        overstock = products[
            products["Stock"] > 30
        ]

        if overstock.empty:

            return jsonify({
                "answer":
                    "No products currently exceed the "
                    "overstock threshold of 30 units.",

                "evidence": {
                    "threshold": 30
                },

                "recommendation":
                    "Continue monitoring inventory levels."
            })

        items = []

        for _, row in overstock.iterrows():

            items.append(
                f'{row["Product_Name"]}: '
                f'{int(row["Stock"])} units'
            )

        return jsonify({
            "answer":
                "Overstocked products: "
                + ", ".join(items)
                + ".",

            "evidence": {
                "threshold": 30,

                "products": [
                    {
                        "product":
                            row["Product_Name"],

                        "stock":
                            int(row["Stock"]),

                        "store":
                            row["Store"]
                    }

                    for _, row
                    in overstock.iterrows()
                ]
            },

            "recommendation":
                "Consider promotions or reducing future "
                "purchases for overstocked products."
        })


    # =====================================================
    # BEST SELLING
    # =====================================================

    if (
        "best selling" in q
        or "top selling" in q
        or "best products" in q
        or "top products" in q
    ):

        best = (
            sales.groupby("Product_Name")["Quantity"]
            .sum()
            .sort_values(ascending=False)
            .head(3)
        )

        items = []

        for name, quantity in best.items():

            items.append(
                f"{name}: {int(quantity)} units"
            )

        return jsonify({
            "answer":
                "Top-selling products: "
                + ", ".join(items)
                + ".",

            "evidence": {
                "products": [
                    {
                        "product": name,
                        "units_sold": int(quantity)
                    }

                    for name, quantity
                    in best.items()
                ]
            },

            "recommendation":
                "Maintain sufficient stock for the "
                "top-selling products."
        })


    # =====================================================
    # POOR PERFORMING
    # =====================================================

    if (
        "performing poorly" in q
        or "poor performing" in q
        or "poorly performing" in q
        or "poor performance" in q
        or "worst performing" in q
        or "worst selling" in q
        or "poor products" in q
        or "underperforming" in q
        or "under performing" in q
    ):

        poor = (
            sales.groupby("Product_Name")["Quantity"]
            .sum()
            .sort_values(ascending=True)
            .head(3)
        )

        items = []

        for name, quantity in poor.items():

            items.append(
                f"{name}: {int(quantity)} units sold"
            )

        return jsonify({
            "answer":
                "The following products are performing poorly: "
                + ", ".join(items)
                + ".",

            "evidence": {
                "products": [
                    {
                        "product": name,
                        "units_sold": int(quantity)
                    }

                    for name, quantity
                    in poor.items()
                ]
            },

            "recommendation":
                "Consider promotions, pricing changes, "
                "or reducing new purchases for these products."
        })


    # =====================================================
    # SALES SPIKES / DROPS
    # =====================================================

    if (
        "sales spike" in q
        or "sales spikes" in q
        or "sales increase" in q
        or "sales increases" in q
        or "sales drop" in q
        or "sales drops" in q
        or "sales decrease" in q
        or "sales decreases" in q
        or "increased sales" in q
        or "decreased sales" in q
    ):

        min_date = sales["Date"].min()
        max_date = sales["Date"].max()

        middle_date = (
            min_date
            + (max_date - min_date) / 2
        )

        first_period = sales[
            sales["Date"] <= middle_date
        ]

        second_period = sales[
            sales["Date"] > middle_date
        ]

        first_units = (
            first_period
            .groupby("Product_Name")["Quantity"]
            .sum()
        )

        second_units = (
            second_period
            .groupby("Product_Name")["Quantity"]
            .sum()
        )

        comparison = pd.DataFrame({
            "first": first_units,
            "second": second_units
        }).fillna(0)

        comparison["change"] = (
            comparison["second"]
            - comparison["first"]
        )

        comparison["change_percent"] = comparison.apply(
            lambda row:
                (
                    (
                        row["second"]
                        - row["first"]
                    )
                    / row["first"]
                    * 100
                )
                if row["first"] > 0
                else 100,
            axis=1
        )

        is_drop = (
            "drop" in q
            or "decrease" in q
            or "decreased" in q
        )

        if is_drop:

            selected = comparison[
                comparison["change"] < 0
            ].sort_values("change")

        else:

            selected = comparison[
                comparison["change"] > 0
            ].sort_values(
                "change",
                ascending=False
            )

        selected = selected.head(3)

        if selected.empty:

            message = (
                "No significant sales drops were found."
                if is_drop
                else
                "No significant sales spikes were found."
            )

            return jsonify({
                "answer": message,

                "evidence": {
                    "first_period":
                        str(min_date.date()),

                    "second_period":
                        str(max_date.date())
                },

                "recommendation":
                    "Continue monitoring sales trends."
            })

        items = []
        evidence_products = []

        for name, row in selected.iterrows():

            items.append(
                f'{name}: '
                f'{int(row["first"])} to '
                f'{int(row["second"])} units '
                f'({row["change_percent"]:.1f}% change)'
            )

            evidence_products.append({
                "product": name,

                "first_period_units":
                    int(row["first"]),

                "second_period_units":
                    int(row["second"]),

                "change_percent":
                    round(
                        float(
                            row["change_percent"]
                        ),
                        1
                    )
            })

        if is_drop:

            answer = (
                "Products showing sales drops: "
                + "; ".join(items)
                + "."
            )

            recommendation = (
                "Investigate pricing, promotions, customer "
                "demand, or stock availability for products "
                "with falling sales."
            )

        else:

            answer = (
                "Products showing sales spikes: "
                + "; ".join(items)
                + "."
            )

            recommendation = (
                "Ensure sufficient stock and investigate "
                "the reasons behind the sales increase."
            )

        return jsonify({
            "answer": answer,

            "evidence": {
                "first_period":
                    str(min_date.date()),

                "second_period":
                    str(max_date.date()),

                "products":
                    evidence_products
            },

            "recommendation":
                recommendation
        })


    # =====================================================
    # STOCK-OUT PREDICTION
    # =====================================================

    if (
        "stock out" in q
        or "stockout" in q
        or "may run out" in q
        or "will run out" in q
        or "run out soon" in q
        or "running out soon" in q
        or "stock-out" in q
        or "stock out soon" in q
        or "products may run out" in q
        or "inventory risk" in q
    ):

        predictions, error = (
            stock_out_prediction()
        )

        if error:

            return jsonify({
                "answer": error,

                "evidence": {},

                "recommendation":
                    "Provide valid sales data before "
                    "making a stock-out prediction."
            })

        risky = [
            item

            for item in predictions

            if item[
                "Estimated_Days_Remaining"
            ] <= 7
        ]

        if not risky:

            return jsonify({
                "answer":
                    "No products are estimated to run "
                    "out within the next 7 days based "
                    "on the available sales velocity.",

                "evidence": {
                    "prediction_period": 7,

                    "sales_start":
                        str(
                            sales["Date"]
                            .min()
                            .date()
                        ),

                    "sales_end":
                        str(
                            sales["Date"]
                            .max()
                            .date()
                        ),

                    "products_checked":
                        len(predictions)
                },

                "recommendation":
                    "Continue monitoring stock and "
                    "daily sales velocity."
            })

        items = []

        for item in risky[:5]:

            items.append(
                f'{item["Product_Name"]}: '
                f'{item["Current_Stock"]} units in stock, '
                f'{item["Average_Daily_Sales"]:.2f} units/day, '
                f'estimated '
                f'{item["Estimated_Days_Remaining"]:.1f} '
                f'days remaining'
            )

        return jsonify({
            "answer":
                "Products that may run out within 7 days: "
                + "; ".join(items)
                + ".",

            "evidence": {
                "threshold_days": 7,

                "sales_start":
                    str(
                        sales["Date"]
                        .min()
                        .date()
                    ),

                "sales_end":
                    str(
                        sales["Date"]
                        .max()
                        .date()
                    ),

                "products":
                    risky[:5]
            },

            "recommendation":
                "Prioritize replenishment for products "
                "with the fewest estimated days of stock remaining."
        })


    # =====================================================
    # DAILY INVENTORY ALERTS
    # =====================================================

    if (
        "daily alert" in q
        or "daily alerts" in q
        or "inventory alert" in q
        or "inventory alerts" in q
        or "what needs attention" in q
        or "what should i do today" in q
        or "today's inventory" in q
        or "todays inventory" in q
        or "inventory status" in q
    ):

        alerts = generate_inventory_alerts()

        if not alerts:

            return jsonify({
                "answer":
                    "No immediate inventory alerts were generated from the available data.",

                "evidence": {
                    "products_checked":
                        int(
                            products[
                                "Product_ID"
                            ].nunique()
                        )
                },

                "recommendation":
                    "Continue monitoring sales and stock levels."
            })

        critical = [
            a for a in alerts
            if a["status"] == "CRITICAL"
        ]

        stock_risk = [
            a for a in alerts
            if a["status"] == "STOCK-OUT RISK"
        ]

        reorder = [
            a for a in alerts
            if a["status"] == "REORDER SOON"
        ]

        overstock = [
            a for a in alerts
            if a["status"] == "OVERSTOCK"
        ]

        summary_parts = []

        if critical:
            summary_parts.append(
                f"{len(critical)} critical"
            )

        if stock_risk:
            summary_parts.append(
                f"{len(stock_risk)} stock-out risk"
            )

        if reorder:
            summary_parts.append(
                f"{len(reorder)} reorder soon"
            )

        if overstock:
            summary_parts.append(
                f"{len(overstock)} overstock"
            )

        return jsonify({
            "answer":
                "Daily inventory alerts: "
                + ", ".join(summary_parts)
                + ".",

            "evidence": {
                "total_alerts":
                    len(alerts),

                "alerts":
                    alerts
            },

            "recommendation":
                "Handle CRITICAL and STOCK-OUT RISK alerts first, "
                "then plan replenishment for REORDER SOON items. "
                "Review OVERSTOCK items for promotions or reduced purchasing."
        })


    # =====================================================
    # NON-MOVING STOCK
    # =====================================================

    if (
        "non-moving" in q
        or "non moving" in q
        or "not selling" in q
        or "not selling products" in q
        or "no sales" in q
        or "never sold" in q
    ):

        sold_products = set(
            sales["Product_ID"].unique()
        )

        non_moving = products[
            ~products["Product_ID"]
            .isin(sold_products)
        ]

        if non_moving.empty:

            return jsonify({
                "answer":
                    "No completely non-moving products "
                    "were found in the available sales data.",

                "evidence": {
                    "products_checked":
                        int(
                            products[
                                "Product_ID"
                            ].nunique()
                        ),

                    "products_with_sales":
                        int(
                            len(sold_products)
                        )
                },

                "recommendation":
                    "Continue monitoring products with very low sales."
            })

        items = []

        for _, row in non_moving.iterrows():

            items.append(
                f'{row["Product_Name"]}: '
                f'{int(row["Stock"])} units in stock'
            )

        return jsonify({
            "answer":
                "Non-moving products: "
                + ", ".join(items)
                + ".",

            "evidence": {
                "products": [
                    {
                        "product":
                            row["Product_Name"],

                        "stock":
                            int(row["Stock"])
                    }

                    for _, row
                    in non_moving.iterrows()
                ]
            },

            "recommendation":
                "Consider promotions, transfers, "
                "or reducing future purchases for non-moving products."
        })


    # =====================================================
    # PRODUCT SEARCH
    # =====================================================

    product_match = None

    for _, row in products.iterrows():

        product_name = str(
            row["Product_Name"]
        ).lower()

        if product_name in q:

            product_match = row
            break

    if product_match is not None:

        product_id = (
            product_match["Product_ID"]
        )

        product_sales = sales[
            sales["Product_ID"] == product_id
        ]

        units_sold = int(
            product_sales["Quantity"].sum()
        )

        revenue = float(
            product_sales["Revenue"].sum()
        )

        stock = int(
            product_match["Stock"]
        )

        return jsonify({
            "answer":
                f'{product_match["Product_Name"]} has '
                f'{stock} units in stock, '
                f'{units_sold} units sold, '
                f'and revenue of ₹{revenue:,.0f}.',

            "evidence": {
                "product":
                    product_match["Product_Name"],

                "stock":
                    stock,

                "units_sold":
                    units_sold,

                "revenue":
                    revenue
            },

            "recommendation":
                "Use the sales and stock figures to "
                "plan replenishment and promotions."
        })


    # =====================================================
    # UNKNOWN QUESTION
    # =====================================================

    return jsonify({
        "answer":
            "I cannot answer that reliably from the "
            "available sales and inventory data.",

        "evidence": {
            "available_data": [
                "sales",
                "inventory",
                "revenue",
                "product performance",
                "sales spikes",
                "sales drops",
                "non-moving stock",
                "stock-out prediction",
                "daily inventory alerts"
            ]
        },

        "recommendation":
            "Try asking about low stock, overstock, "
            "best-selling products, poor-performing products, "
            "sales spikes, sales drops, non-moving stock, "
            "stock-out prediction, or daily inventory alerts."
    })


# =========================================================
# RUN SERVER
# =========================================================

if __name__ == "__main__":

    print("=" * 60)
    print("Retail Sales & Inventory Copilot")
    print("Server: http://127.0.0.1:8000")
    print("=" * 60)

    app.run(
        host="0.0.0.0",
        port=8000,
        debug=False
    )