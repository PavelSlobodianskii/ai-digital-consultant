EXAMPLES = [
    {
        "id": "ap-invoices",
        "title": "Accounts payable invoice posting",
        "blurb": "Structured ERP data — likely rules, not a chatbot.",
        "industry": "Manufacturing",
        "volume_note": "About 800 supplier invoices per month",
        "tools_note": "SAP, shared Excel tracker, email from vendors",
        "data_shape": "structured",
        "judgment_level": "rare",
        "process_text": (
            "Our AP team posts supplier invoices into SAP. Most invoices already have a purchase "
            "order and should three-way match on PO number, quantity, and amount. If the amount is "
            "under $5,000 and the match is exact, clerks post immediately. If the variance is over "
            "2% or there is no PO, a manager approval is required using a checklist. Exceptions are "
            "rare. Clerks copy values from a spreadsheet into SAP form fields. We want to know if AI "
            "would help or if ordinary automation is enough."
        ),
    },
    {
        "id": "support-inbox",
        "title": "Customer support email triage",
        "blurb": "Unstructured language — likely AI or hybrid intake.",
        "industry": "SaaS",
        "volume_note": "1,200 emails per week across 4 inboxes",
        "tools_note": "Gmail, Zendesk, Slack",
        "data_shape": "unstructured",
        "judgment_level": "frequent",
        "process_text": (
            "Support agents read free-text customer emails, interpret intent, and classify tickets "
            "into billing, bugs, how-to, and churn risk. Many emails are ambiguous, mix several "
            "issues, or include screenshots and PDF attachments. Agents also write a short summary "
            "and a first-draft reply. There is no reliable dropdown or form — customers write in "
            "natural language. We currently do this entirely by hand and miss urgent churn language."
        ),
    },
    {
        "id": "insurance-claims",
        "title": "Insurance first-notice-of-loss",
        "blurb": "Rules for most claims, judgment on exceptions — hybrid.",
        "industry": "Insurance",
        "volume_note": "300 FNOL claims per week",
        "tools_note": "Guidewire, email, phone transcripts",
        "data_shape": "mixed",
        "judgment_level": "frequent",
        "process_text": (
            "First notice of loss arrives by web form, email, and call transcripts. About 80% of "
            "claims follow routing rules: if coverage type is auto and estimate is under a policy "
            "threshold, assign to a junior adjuster. The remaining cases need interpretation of "
            "unstructured descriptions, photos, and ambiguous liability language. Exceptions and "
            "edge cases are common. Supervisors review escalations. We do not want an AI chatbot "
            "replacing the coverage rules that already work."
        ),
    },
    {
        "id": "password-reset",
        "title": "IT password reset and access requests",
        "blurb": "Deterministic IT workflow — should not need an LLM.",
        "industry": "Internal IT",
        "volume_note": "90 tickets per day",
        "tools_note": "ServiceNow, Active Directory",
        "data_shape": "structured",
        "judgment_level": "rare",
        "process_text": (
            "Employees submit a ServiceNow catalog item to reset a password or request application "
            "access. Fields are dropdowns: application name, role, manager, and duration. If the "
            "manager is in the system of record and the role is on an approved checklist, IT always "
            "grants access. If the role is privileged, a security group approval is required. There "
            "is no free-text judgment. We were told to 'add AI agents' to this process."
        ),
    },
]
