import re
from sqlalchemy import text

def fetch_sql_context(session, user_q_lower, emp_id, ticket_id):
    """
    Analyzes user query intent, dynamically inspects JSONB schemas,
    and runs database queries to construct a clean context layer.
    """
    sql_context_texts = []
    citations = []
    
    # 1. Dynamic Schema Inspection: Safely establish key names
    dept_key = "Department"
    id_key = "EmployeeID"
    salary_key = "Salary"
    name_key = "Name"
    exp_key = "ExperienceYears"  # FIX: Added dynamic key for experience
    
    try:
        sample = session.execute(text("SELECT row_data FROM cleaned_csv_records LIMIT 1")).fetchone()
        if sample and sample[0]:
            for k in sample[0].keys():
                k_lower_check = k.lower()
                if k_lower_check in ["department", "dept"]: dept_key = k
                elif k_lower_check in ["employeeid", "employee_id", "emp_id", "id"]: id_key = k
                elif "salary" in k_lower_check: salary_key = k
                elif "name" in k_lower_check: name_key = k
                elif "experience" in k_lower_check: exp_key = k
    except Exception as schema_err:
        print(f"Schema discovery warning: {schema_err}")

    # =========================================================================
    # INTENT ROUTING & HISTORY BLEED FIX
    # =========================================================================
    name_matches = re.findall(r'(employee[_\s]?\d+)', user_q_lower, re.IGNORECASE)
    target_emp_name = name_matches[-1].replace(" ", "_") if name_matches else None

    # =========================================================================
    # A. DYNAMIC MULTI-FIELD JSONB LOOKUP (ID, Name, City, Dept, Performance, Experience)
    # =========================================================================
    conditions = []
    params = {}

    comp_pattern = r'\b(more|higher|greater|less|lower|above|below|over|under)\b.*\b(than|him|his|her|them|employee)\b'
    is_comp_query = bool(re.search(comp_pattern, user_q_lower, re.IGNORECASE))

    if target_emp_name and not is_comp_query:
        conditions = [f"row_data->>'{name_key}' ILIKE :ename"]
        params = {"ename": f"%{target_emp_name}%"}
    else:
        if emp_id:
            conditions.append(f"row_data->>'{id_key}' = :eid")
            params["eid"] = str(emp_id)
            
        # 3. Filter by City
        city_match = re.search(r'\b(delhi|mumbai|hyderabad|pune|bengaluru|bangalore)\b', user_q_lower, re.IGNORECASE)
        if city_match:
            matched_city = city_match.group(1).lower()
            conditions.append("(row_data->>'City' ILIKE :city OR row_data->>'City' ILIKE :city_alt)")
            if matched_city in ["bengaluru", "bangalore"]:
                params["city"] = "%bengaluru%"
                params["city_alt"] = "%bangalore%"
            else:
                params["city"] = f"%{matched_city}%"
                params["city_alt"] = f"%{matched_city}%"

        # 4. Filter by Department
        dept_match = re.search(r'\b(sales|hr|finance|support|engineering)\b', user_q_lower, re.IGNORECASE)
        if dept_match:
            conditions.append(f"row_data->>'{dept_key}' ILIKE :dept")
            params["dept"] = f"%{dept_match.group(1)}%"
            
        # 5. Filter by Performance Rating (FIX: Prevent 'average salary' from triggering performance filter)
        perf_match = re.search(r'\b(excellent|good|average(?!\s*salary))\b', user_q_lower, re.IGNORECASE)
        if perf_match:
            conditions.append("row_data->>'Performance' ILIKE :perf")
            params["perf"] = f"%{perf_match.group(1)}%"

        # 6. FIX: Filter by Experience Years (Handles "> 5 years", "over 5 years", etc.)
        exp_match = re.search(r'(?:over|more than|>|greater than)\s*(\d+)\s*(?:years?|yrs?)', user_q_lower, re.IGNORECASE)
        if exp_match:
            conditions.append(f"CAST(NULLIF(regexp_replace(row_data->>'{exp_key}', '[^0-9.]', '', 'g'), '') AS NUMERIC) > :exp_years")
            params["exp_years"] = int(exp_match.group(1))

    # Shared WHERE clause for both single records and aggregations
    where_clause = " AND ".join(conditions) if conditions else "1=1"

    # Execute dynamic search if conditions exist AND it's not a direct comparison query
    if conditions and not is_comp_query:
        try:
            # 1. Get Total Count of matching records
            count_query = text(f"SELECT COUNT(*) FROM cleaned_csv_records WHERE {where_clause}")
            total_count = session.execute(count_query, params).scalar() or 0
            
            # 2. Fetch sample rows (e.g., top 5)
            sql_query = text(f"SELECT row_data FROM cleaned_csv_records WHERE {where_clause} LIMIT 5")
            db_rows = session.execute(sql_query, params).fetchall()
            
            if db_rows:
                sample_records = []
                for db_row in db_rows:
                    if db_row and db_row[0]:
                        record_str = ", ".join([f"{k}: {v}" for k, v in db_row[0].items()])
                        sample_records.append(record_str)
                
                joined_samples = "\n".join(sample_records)
                remaining_count = max(0, total_count - len(db_rows))
                
                ai_instruction = (
                    f"\n\n*** MANDATORY AI FORMATTING RULES ***\n"
                    f"1. State clearly that there are a total of {total_count} matching employees.\n"
                    f"2. List a few sample employees from the provided list, and explicitly state that there are {remaining_count} more matching records.\n"
                    f"3. Answer in a simple, natural paragraph. STRICTLY DO NOT use bullet points, dashes, or lists.\n"
                    f"4. Provide ONLY the requested information without any conversational filler."
                )
                
                sql_context_texts.append(f"[Database Record]: Total Count -> {total_count}. Samples:\n{joined_samples}{ai_instruction}")
                
                if "Cleaned CSV Dataset" not in citations:
                    citations.append("Cleaned CSV Dataset")
        except Exception as sql_err:
            print(f"Database Query Warning (JSONB Dynamic Record): {sql_err}")

    # =========================================================================
    # B. Aggregate / Department-Wide JSONB Lookup (Counts AND Averages)
    # =========================================================================
    agg_keywords = ["department", "dept", "count", "number of", "how many", "total", "average", "avg"]
    if not emp_id and any(kw in user_q_lower for kw in agg_keywords) and not is_comp_query:
        try:
            is_dept_grouping = any(kw in user_q_lower for kw in ["department", "dept", "each"])
            
            if is_dept_grouping:
                sql_query = text(f"""
                    SELECT 
                        row_data->>'{dept_key}' AS dept, 
                        COUNT(*),
                        ROUND(AVG(CAST(NULLIF(regexp_replace(row_data->>'{salary_key}', '[^0-9.]', '', 'g'), '') AS NUMERIC)), 0) AS avg_salary
                    FROM cleaned_csv_records 
                    WHERE row_data->>'{dept_key}' IS NOT NULL AND ({where_clause})
                    GROUP BY row_data->>'{dept_key}'
                """)
                db_rows = session.execute(sql_query, params).fetchall()
                if db_rows:
                    dept_stats = " | ".join([f"{row[0]}: {row[1]} employees (Avg Salary: ${int(row[2]):,})" if row[2] else f"{row[0]}: {row[1]} employees" for row in db_rows])
                    sql_context_texts.append(f"[Database Aggregation]: Dataset Breakdown -> {dept_stats}")
                    if "Cleaned CSV Dataset" not in citations: citations.append("Cleaned CSV Dataset")
            else:
                sql_query = text(f"""
                    SELECT 
                        COUNT(*),
                        ROUND(AVG(CAST(NULLIF(regexp_replace(row_data->>'{salary_key}', '[^0-9.]', '', 'g'), '') AS NUMERIC)), 0) AS avg_salary
                    FROM cleaned_csv_records 
                    WHERE {where_clause}
                """)
                db_rows = session.execute(sql_query, params).fetchall()
                if db_rows and db_rows[0][0] > 0:
                    cnt = db_rows[0][0]
                    avg_sal = f"${int(db_rows[0][1]):,}" if db_rows[0][1] else "N/A"
                    sql_context_texts.append(f"[Database Aggregation]: Total matching records count -> {cnt} employees. Average Salary -> {avg_sal}")
                    if "Cleaned CSV Dataset" not in citations: citations.append("Cleaned CSV Dataset")
        except Exception as sql_err:
            print(f"Database Query Warning (JSONB Aggregation): {sql_err}")

    # =========================================================================
    # C. Advanced Analytics (Highest / Lowest Salary Logic & Top/Bottom Rankings)
    # =========================================================================
    salary_keywords = ["highest", "max", "maximum", "top", "lowest", "min", "minimum", "bottom", "least"]
    # FIX: Added "earner" and "income" to the trigger list below
    if any(kw in user_q_lower for kw in salary_keywords) and any(kw in user_q_lower for kw in ["salary", "paid", "pay", "earning", "earner", "income", "employee"]):
        try:
            is_lowest = any(kw in user_q_lower for kw in ["lowest", "min", "minimum", "bottom", "least"])
            sort_order = "ASC" if is_lowest else "DESC"
            rank_label = "Lowest" if is_lowest else "Highest"

            limit_val = 10 if "10" in user_q_lower else 5
            is_per_dept = any(kw in user_q_lower for kw in ["dept", "department", "each", "per"])
            
            target_dept = None
            dept_match = re.search(r'\b(sales|hr|finance|support|engineering)\b', user_q_lower, re.IGNORECASE)
            if dept_match:
                target_dept = dept_match.group(1)

            if is_per_dept and not target_dept:
                sql_query = text(f"""
                    WITH RankedSalaries AS (
                        SELECT 
                            row_data->>'{name_key}' AS emp_name,
                            row_data->>'{dept_key}' AS dept,
                            CAST(NULLIF(regexp_replace(row_data->>'{salary_key}', '[^0-9.]', '', 'g'), '') AS NUMERIC) AS salary_math,
                            ROW_NUMBER() OVER(
                                PARTITION BY row_data->>'{dept_key}' 
                                ORDER BY CAST(NULLIF(regexp_replace(row_data->>'{salary_key}', '[^0-9.]', '', 'g'), '') AS NUMERIC) {sort_order}
                            ) as rnk
                        FROM cleaned_csv_records
                        WHERE row_data->>'{salary_key}' IS NOT NULL
                    )
                    SELECT emp_name, dept, salary_math 
                    FROM RankedSalaries 
                    WHERE rnk <= {limit_val}
                    ORDER BY dept, salary_math {sort_order}
                """)
                db_rows = session.execute(sql_query).fetchall()
            else:
                where_conditions = [f"row_data->>'{salary_key}' IS NOT NULL"]
                params_analytics = {}
                
                if target_dept:
                    where_conditions.append(f"row_data->>'{dept_key}' ILIKE :analytics_dept")
                    params_analytics["analytics_dept"] = f"%{target_dept}%"

                where_clause_analytics = " WHERE " + " AND ".join(where_conditions)

                sql_query = text(f"""
                    SELECT 
                        row_data->>'{name_key}' AS emp_name,
                        row_data->>'{dept_key}' AS dept,
                        CAST(NULLIF(regexp_replace(row_data->>'{salary_key}', '[^0-9.]', '', 'g'), '') AS NUMERIC) AS salary_math
                    FROM cleaned_csv_records
                    {where_clause_analytics}
                    ORDER BY CAST(NULLIF(regexp_replace(row_data->>'{salary_key}', '[^0-9.]', '', 'g'), '') AS NUMERIC) {sort_order}
                    LIMIT {limit_val}
                """)
                db_rows = session.execute(sql_query, params_analytics).fetchall()
            
            if db_rows:
                formatted_rows = [f"{idx+1}. {row[0]} ({row[1]} Dept): ${int(row[2]):,}" if row[2] else f"{idx+1}. {row[0]} ({row[1]} Dept): $0" for idx, row in enumerate(db_rows)]
                stats = "\n".join(formatted_rows)
                
                dept_str = f" in {target_dept.upper()}" if target_dept else ""
                context_string = (
                    f"Direct Answer Context: Top {limit_val} {rank_label} Paid Employees{dept_str}:\n{stats}\n"
                    f"CRITICAL INSTRUCTION FOR AI: Output the employees EXACTLY in the 1 to {len(db_rows)} order listed above in a simple paragraph format. Do NOT use bullet points."
                )
                sql_context_texts.append(context_string)
                if "Cleaned CSV Dataset" not in citations: citations.append("Cleaned CSV Dataset")
        except Exception as sql_err:
            print(f"Database Query Warning (Analytics): {sql_err}")

    # =========================================================================
    # D. Relational Ticket Table Lookup
    # =========================================================================
    if ticket_id or any(kw in user_q_lower for kw in ["ticket", "customer"]):
        try:
            if ticket_id:
                sql_query = text("SELECT id, title, customer_name, status, description FROM tickets WHERE id = :tid")
                params_tkt = {"tid": ticket_id}
            else:
                sql_query = text("SELECT id, title, customer_name, status, description FROM tickets ORDER BY created_at DESC LIMIT 5")
                params_tkt = {}
            
            db_rows = session.execute(sql_query, params_tkt).fetchall()
            for row in db_rows:
                sql_context_texts.append(f"[Ticket Record]: ID {row[0]} | Title: {row[1]} | Customer: {row[2]} | Status: {row[3]} | Details: {row[4]}")
                if "Tickets Database" not in citations: citations.append("Tickets Database")
        except Exception as sql_err:
            print(f"Database Query Warning (Tickets): {sql_err}")

    # =========================================================================
    # E. Comparative Salary Queries (Handles "more than him", "Employee_108", etc.)
    # =========================================================================
    if is_comp_query:
        try:
            emp_target = None
            
            target_check = re.findall(r'employee[_\s]?(\d+)', user_q_lower, re.IGNORECASE)
            if target_check:
                emp_target = f"Employee_{target_check[-1]}"

            if not emp_target:
                fb_row = session.execute(text(f"SELECT row_data->>'{name_key}' FROM cleaned_csv_records WHERE row_data->>'{name_key}' IS NOT NULL ORDER BY id DESC LIMIT 1")).fetchone()
                if fb_row: emp_target = fb_row[0]

            if emp_target:
                step1_query = text(f"""
                    SELECT CAST(NULLIF(regexp_replace(row_data->>'{salary_key}', '[^0-9.]', '', 'g'), '') AS NUMERIC) 
                    FROM cleaned_csv_records 
                    WHERE row_data->>'{name_key}' ILIKE :ename LIMIT 1
                """)
                target_salary_row = session.execute(step1_query, {"ename": f"%{emp_target}%"}).fetchone()
                
                if target_salary_row and target_salary_row[0] is not None:
                    target_salary = target_salary_row[0]
                    
                    is_less = bool(re.search(r'\b(less|lower|below|under)\b', user_q_lower, re.IGNORECASE))
                    operator = "<" if is_less else ">"
                    
                    comp_conditions = [f"CAST(NULLIF(regexp_replace(row_data->>'{salary_key}', '[^0-9.]', '', 'g'), '') AS NUMERIC) {operator} {target_salary}"]
                    comp_params = {}
                    
                    city_match = re.search(r'\b(delhi|mumbai|hyderabad|pune|bengaluru|bangalore)\b', user_q_lower, re.IGNORECASE)
                    if city_match:
                        matched_city = city_match.group(1).lower()
                        comp_conditions.append("(row_data->>'City' ILIKE :city OR row_data->>'City' ILIKE :city_alt)")
                        if matched_city in ["bengaluru", "bangalore"]:
                            comp_params["city"] = "%bengaluru%"
                            comp_params["city_alt"] = "%bangalore%"
                        else:
                            comp_params["city"] = f"%{matched_city}%"
                            comp_params["city_alt"] = f"%{matched_city}%"

                    dept_match = re.search(r'\b(sales|hr|finance|support|engineering)\b', user_q_lower, re.IGNORECASE)
                    if dept_match:
                        comp_conditions.append(f"row_data->>'{dept_key}' ILIKE :dept")
                        comp_params["dept"] = f"%{dept_match.group(1)}%"
                        
                    comp_conditions.append(f"row_data->>'{name_key}' NOT ILIKE :exclude_name")
                    comp_params["exclude_name"] = f"%{emp_target}%"
                        
                    comp_where = " AND ".join(comp_conditions)

                    count_query = text(f"SELECT COUNT(*) FROM cleaned_csv_records WHERE {comp_where}")
                    total_count = session.execute(count_query, comp_params).scalar() or 0

                    step2_query = text(f"""
                        SELECT row_data->>'{name_key}', row_data->>'{salary_key}', row_data->>'{dept_key}', row_data->>'City' 
                        FROM cleaned_csv_records 
                        WHERE {comp_where} 
                        ORDER BY CAST(NULLIF(regexp_replace(row_data->>'{salary_key}', '[^0-9.]', '', 'g'), '') AS NUMERIC) DESC 
                        LIMIT 10
                    """)
                    
                    comp_rows = session.execute(step2_query, comp_params).fetchall()
                    
                    city_str = f" in {city_match.group(1).title()}" if city_match else ""
                    if comp_rows:
                        formatted_comp = ", ".join([f"{r[0]} (${r[1]})" for r in comp_rows])
                        context_string = (
                            f"Direct Answer Context: There are a total of {total_count} employees{city_str} earning {operator} ${target_salary} (Base Target: {emp_target}).\n"
                            f"Top sample matching employees:\n{formatted_comp}\n"
                            f"CRITICAL INSTRUCTION: First, state EXACTLY 'There are a total of {total_count} employees matching this criteria.' Then, list the sample employees in a simple paragraph format. Do NOT use bullet points."
                        )
                        sql_context_texts.append(context_string)
                    else:
                        context_string = (
                            f"Direct Answer Context: There are 0 employees{city_str} earning {operator} ${target_salary} (Base Target: {emp_target})."
                        )
                        sql_context_texts.append(context_string)
                    
                    if "Cleaned CSV Dataset" not in citations: citations.append("Cleaned CSV Dataset")
        except Exception as sql_err:
            print(f"Database Query Warning (Comparative): {sql_err}")

    return sql_context_texts, citations