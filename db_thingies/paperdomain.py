"""
Paper Domain Classifier — Database Edition
============================================
Reads papers from the `scopuss` MySQL database (C.Tech department only),
classifies each paper into a research domain, and writes the result back
into the `domain` column of the `papers` table.

USAGE
-----
    python paperdomain_db.py              # uses config below
    python paperdomain_db.py --dry-run   # preview without writing to DB

DATABASE ASSUMPTIONS
--------------------
The script expects the following in the `scopuss` database:

    papers table (minimum columns required):
        - id               PRIMARY KEY  (used for UPDATE)
        - title            TEXT / VARCHAR
        - publication_name TEXT / VARCHAR  (journal / conference name)
        - domain           VARCHAR(100)   (this column is updated)

    Department filter — ONE of these schemas is auto-detected:
        Option A:  papers.department  column  (e.g. "C.Tech" / "Computing Technology")
        Option B:  papers.faculty_id  → faculty.id, faculty.department column
        Option C:  papers.scopus_id   → faculty.scopus_id, faculty.department column

    If your schema is different, set DEPARTMENT_QUERY below manually.
"""

import re
import sys
import os
from collections import Counter

# ─────────────────────────────────────────────────────────────────────────────
# DATABASE CONFIG  ← edit these
# ─────────────────────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host":     "localhost",
    "port":     3307,
    "user":     "root",          # your MySQL username
    "password": "",              # your MySQL password
    "database": "scopuss",
}

# Department name(s) to match — any paper whose department contains one of
# these strings (case-insensitive) will be classified.
DEPARTMENT_KEYWORDS = ["c.tech", "computing technology", "computing technologies"]

# Minimum classification score — papers scoring below this stay blank
MIN_SCORE = 5.0

# Set to True to print what would change without touching the database
DRY_RUN = "--dry-run" in sys.argv

# ─────────────────────────────────────────────────────────────────────────────
# DOMAIN KEYWORD DEFINITIONS
# ─────────────────────────────────────────────────────────────────────────────
DOMAIN_KEYWORDS = {

    "Accelerated Computing": [
        ("gpu-accelerat", 5), ("cuda", 5), ("opencl", 5), ("tpu", 4.5),
        ("fpga", 4.5), ("tensor core", 5), ("gpu cluster", 5),
        ("gpu computing", 5), ("gpu-based", 4), ("gpu parallel", 5),
        ("high performance computing", 4), ("hpc ", 4), ("hpc-", 4),
        ("parallel processing", 3.5), ("hardware acceleration", 4),
        ("heterogeneous computing", 4), ("manycore", 4), ("many-core", 4),
        ("multicore processor", 3.5), ("simd", 4),
        ("supercomputing", 4), ("supercomputer", 4),
        ("cluster computing performance", 4),
        ("memory hierarchy optim", 3.5), ("cache optim", 3.5),
        ("cpu vectorization", 3.5), ("simd vectorization", 4),
        ("compute shader", 4), ("parallel computation", 3),
        ("distributed training", 3), ("model parallelism", 3.5),
        ("data parallelism", 3.5), ("pipeline parallelism", 3.5),
    ],

    "Advanced Multilingual Computing": [
        ("multilingual", 5), ("low-resource language", 5), ("cross-lingual", 5),
        ("code-switching", 5), ("machine translation", 5),
        ("neural machine translation", 5), ("indic language", 5),
        ("language model", 4), ("large language model", 5), ("llm", 4),
        ("natural language processing", 4.5), (" nlp ", 4), ("nlp-", 4),
        ("text classification", 3.5), ("named entity recognition", 4),
        (" ner ", 3.5), ("sentiment analysis", 3.5),
        ("question answering", 4), ("text summarization", 4),
        ("language generation", 4), ("word embedding", 4),
        ("bert", 3.5), ("gpt-", 3.5), ("transformer-based language", 4),
        ("speech recognition", 3.5), ("dialogue system", 4),
        ("chatbot", 3.5), ("corpus linguistics", 4),
        ("tokenization", 3.5), ("part-of-speech", 4),
        ("dependency parsing", 4), ("coreference", 4),
        ("semantic role", 4), ("text mining", 3),
        ("information extraction", 3), ("relation extraction", 4),
        ("tamil language", 5), ("hindi language", 5),
        ("arabic nlp", 5), ("bangla", 4), ("telugu", 4), ("kannada", 4),
        ("dravidian", 4), ("devanagari", 4), ("transliteration", 4),
    ],

    "Fintech": [
        ("blockchain", 5), ("cryptocurrency", 5), ("bitcoin", 5),
        ("ethereum", 5), ("smart contract", 5), ("defi", 5),
        ("decentralized finance", 5), ("digital payment", 5),
        ("payment gateway", 5), ("fintech", 5), ("nft", 4.5),
        ("consensus mechanism", 5), ("distributed ledger", 5),
        ("algorithmic trading", 5), ("stock market prediction", 4.5),
        ("stock price prediction", 4.5), ("financial forecasting", 4.5),
        ("credit scoring", 4.5), ("loan default", 4.5),
        ("fraud detection", 4), ("anti-money laundering", 5),
        ("aml detection", 5), ("kyc", 4.5),
        ("robo-advisor", 5), ("portfolio optim", 4.5),
        ("high-frequency trading", 5), ("market microstructure", 4.5),
        ("financial risk", 4), ("insurance claim", 4),
        ("banking transaction", 4), ("credit card fraud", 4.5),
        ("e-payment", 4), ("mobile payment", 4),
        ("crypto exchange", 5), ("token economy", 4),
    ],

    "Geospatial Computing": [
        ("geospatial", 5), ("gis ", 5), ("gis-", 5),
        ("remote sensing", 5), ("satellite image", 5),
        ("land use", 5), ("land cover", 5), ("lidar", 5),
        ("geographic information system", 5),
        ("ndvi", 5), ("hyperspectral image", 5), ("multispectral image", 5),
        ("digital elevation model", 5), ("dem ", 4.5),
        ("aerial image", 5), ("drone mapping", 5),
        ("spatial data", 4), ("spatial analysis", 4),
        ("terrain analysis", 4.5), ("flood mapping", 4.5),
        ("urban heat island", 4.5), ("urban sprawl", 4.5),
        ("change detection", 4), ("vegetation mapping", 4.5),
        ("crop mapping", 4.5), ("soil mapping", 4.5),
        ("geological survey", 4), ("cartography", 4.5),
        ("geolocation", 4), ("geostatistics", 4.5),
        ("point cloud", 3.5), ("3d terrain", 4), ("topographic", 3.5),
    ],

    "Green Computing": [
        ("green computing", 6), ("energy-efficient computing", 5),
        ("data center energy", 5), ("green data center", 6),
        ("carbon footprint computing", 5), ("eco-friendly hardware", 5),
        ("dynamic voltage scaling", 5), ("dvfs", 5),
        ("energy harvesting", 4.5), ("power-aware computing", 5),
        ("energy consumption optim", 4), ("low-power design", 4.5),
        ("power management", 4), ("thermal management", 4),
        ("e-waste", 4.5), ("sustainable it", 5),
        ("server consolidation", 4.5), ("workload consolidation", 4.5),
        ("virtual machine migration", 4), ("vm consolidation", 4.5),
        ("cooling optim", 4), ("green cloud", 5),
        ("battery lifetime", 3.5), ("energy efficiency", 3),
        ("renewable energy integration", 3.5),
    ],

    "Networking": [
        ("5g network", 5), ("6g network", 5), ("5g communication", 5),
        ("6g communication", 5), ("lte network", 5), ("lte-a", 5),
        ("wi-fi", 4.5), ("wlan", 4.5), ("wpan", 4.5),
        ("software defined networking", 5), ("sdn ", 5), ("sdn-", 5),
        ("network function virtualization", 5), ("nfv", 5),
        ("network slicing", 5), ("network protocol", 4.5),
        ("routing protocol", 5), ("network topology", 4.5),
        ("packet switching", 5), ("packet loss", 4.5),
        ("cognitive radio", 5), ("vehicular network", 5),
        ("vanet", 5), ("manet", 5), ("wsn", 4.5),
        ("wireless sensor network", 5), ("internet of things", 4.5),
        (" iot ", 4), ("iot-based", 4), ("iot network", 4.5),
        ("channel estimation", 4.5), ("mimo-ofdm", 5), ("ofdm", 4.5),
        ("beamforming", 5), ("spectrum sensing", 5),
        ("antenna design", 4.5), ("mimo system", 4.5),
        ("interference cancellation", 5), ("channel capacity", 5),
        ("network congestion", 5), ("qos ", 4.5),
        ("intrusion detection system", 4.5), ("ddos attack", 4.5),
        ("network intrusion", 5), ("network traffic classif", 5),
        ("network traffic detect", 5), ("botnet detection", 5),
        ("fog computing", 4.5), ("mobile edge computing", 5),
        ("content delivery network", 5), ("cdn ", 4.5),
        ("load balancing network", 4.5), ("network bandwidth", 4),
        ("peer-to-peer", 4.5), ("p2p network", 5),
        ("tcp/ip", 5), ("network latency", 4),
        ("wireless communication", 4), ("wireless channel", 4),
        ("signal propagation", 4), ("path loss", 4.5),
        ("network security protocol", 4.5),
    ],

    "Quantum Computing": [
        ("quantum computing", 6), ("quantum circuit", 5), ("qubit", 5),
        ("quantum gate", 5), ("quantum entanglement", 5),
        ("quantum algorithm", 5), ("quantum machine learning", 5),
        ("quantum neural network", 5), ("quantum cryptography", 5),
        ("quantum key distribution", 5), ("qkd", 5),
        ("quantum error correction", 5), ("quantum supremacy", 5),
        ("variational quantum eigensolver", 5), ("vqe", 5),
        ("quantum approximate optimization", 5), ("qaoa", 5),
        ("quantum annealing", 5), ("quantum simulation", 5),
        ("quantum teleportation", 5), ("quantum walk", 5),
        ("quantum", 3.5),
    ],

    "Sustainable Computing": [
        ("sustainable computing", 6), ("low-carbon computing", 6),
        ("responsible computing", 5), ("green software engineering", 5),
        ("environmental sustainability in computing", 5),
        ("lifecycle assessment software", 5), ("circular it", 5),
        ("circular economy technology", 4.5),
        ("eco-design software", 5), ("carbon-aware computing", 5),
        ("sustainable development goal", 4),
        ("sdg", 3.5), ("environmental impact computing", 4.5),
        ("sustainable cloud", 4.5), ("sustainable iot", 4.5),
        ("sustainable ai", 4.5), ("sustainable data center", 4.5),
        ("resource-efficient computing", 4),
    ],

    "Theoretical Computing": [
        ("computational complexity", 5), ("np-hard", 5), ("np-complete", 5),
        ("np hard", 5), ("np complete", 5), ("p vs np", 5),
        ("automata theory", 5), ("turing machine", 5), ("turing-complete", 5),
        ("formal language", 5), ("formal verification", 5),
        ("formal method", 4.5), ("model checking", 5),
        ("theorem proving", 5), ("type theory", 5),
        ("lambda calculus", 5), ("pi calculus", 5),
        ("computability", 5), ("decidability", 5),
        ("satisfiability", 5), ("sat solver", 5), ("smt solver", 5),
        ("approximation algorithm", 4.5), ("randomized algorithm", 4.5),
        ("online algorithm", 4.5), ("parameterized complexity", 5),
        ("graph theory", 4), ("combinatorial optimization", 4),
        ("computational geometry", 5), ("algorithmic game theory", 5),
        ("information theory", 4), ("coding theory", 4.5),
        ("time complexity analysis", 4.5), ("space complexity", 4.5),
        ("lower bound proof", 4.5), ("upper bound proof", 4.5),
        ("competitive ratio", 5), ("amortized analysis", 5),
        ("correctness proof", 4), ("loop invariant", 4),
        ("program verification", 4.5), ("static analysis", 4),
        ("abstract interpretation", 5), ("category theory", 5),
        ("finite automata", 5), ("pushdown automata", 5),
        ("context-free grammar", 5), ("regular language", 5),
        ("halting problem", 5), ("polynomial reduction", 4.5),
    ],

    "Visual Computing": [
        ("computer vision", 5), ("image segmentation", 5),
        ("object detection", 4.5), ("object recognition", 4.5),
        ("image classification", 4), ("image recognition", 4.5),
        ("augmented reality", 5), ("virtual reality", 5), ("mixed reality", 5),
        (" ar/vr", 5), ("3d reconstruction", 5), ("depth estimation", 5),
        ("optical flow", 5), ("stereo vision", 5), ("scene understanding", 5),
        ("pose estimation", 5), ("facial recognition", 5),
        ("face detection", 4.5), ("gaze estimation", 5),
        ("video object tracking", 5), ("video segmentation", 5),
        ("point cloud processing", 5), ("mesh generation", 4.5),
        ("rendering pipeline", 5), ("ray tracing", 5),
        ("3d graphics", 5), ("opengl", 5), ("vulkan", 5),
        ("fundus image", 5), ("retinal image", 5), ("oct image", 5),
        ("histopathology image", 5), ("dermoscopy", 5),
        ("endoscopy image", 5), ("colonoscopy", 5),
        ("medical image segmentation", 5), ("medical image classification", 5),
        ("medical image analysis", 5),
        ("x-ray image", 4.5), ("mri segmentation", 4.5),
        ("ct image segmentation", 4.5), ("ultrasound image", 4.5),
        ("image processing", 4), ("feature extraction", 3),
        ("visual feature", 4), ("visual representation", 3.5),
        ("image generation", 4), ("generative image", 4),
        ("super resolution", 4.5), ("image restoration", 4.5),
        ("image denoising", 4.5), ("image enhancement", 4),
        ("visual transformer", 4), ("vision transformer", 4.5),
        ("visual question answering", 4.5), ("visual grounding", 4.5),
        ("gesture recognition", 4), ("sign language recognition", 4.5),
        ("action recognition", 4), ("activity recognition", 3.5),
    ],

    "AI in Healthcare": [
        ("disease diagnosis", 5), ("disease detection", 5), ("disease prediction", 5),
        ("disease classification", 5), ("clinical decision support", 5),
        ("health informatics", 5), ("biomedical informatics", 5),
        ("electronic health record", 5), ("ehr ", 4.5),
        ("medical diagnosis", 5), ("computer-aided diagnosis", 5),
        ("computer-aided detection", 5), ("cad system", 4.5),
        ("healthcare informatics", 5), ("predictive healthcare", 5),
        ("telemedicine", 5), ("iomt", 5), ("internet of medical things", 5),
        ("drug discovery", 5), ("drug interaction", 5),
        ("genomics", 4.5), ("bioinformatics", 5),
        ("patient outcome", 4.5), ("patient monitoring", 4.5),
        ("hospital workflow", 4.5), ("clinical trial", 4.5),
        ("cancer detection", 5), ("cancer classification", 5),
        ("cancer prediction", 5), ("cancer diagnosis", 5),
        ("detection of cancer", 5), ("diagnosis of cancer", 5),
        ("classification of cancer", 5),
        ("tumor detection", 5), ("tumor classification", 5),
        ("tumor segmentation", 5), ("tumour detection", 5),
        ("detection of tumor", 5), ("diagnosis of tumor", 5),
        ("pancreatic cancer", 5), ("prostate cancer", 5),
        ("ovarian cancer", 5), ("gastric cancer", 5),
        ("diabetic retinopathy", 5), ("diabetes prediction", 4.5),
        ("diabetes detection", 4.5), ("diabetes classification", 5),
        ("detection of diabetes", 5), ("prediction of diabetes", 5),
        ("heart disease prediction", 5), ("heart disease detection", 5),
        ("prediction of heart disease", 5), ("detection of heart disease", 5),
        ("cardiac arrhythmia", 5), ("arrhythmia detection", 5),
        ("arrhythmia classification", 5), ("detection of arrhythmia", 5),
        ("alzheimer", 5), ("parkinson", 4.5),
        ("covid-19 detection", 5), ("covid detection", 5),
        ("pneumonia detection", 5), ("detection of pneumonia", 5),
        ("epileptic seizure", 5), ("seizure detection", 5),
        ("detection of epilep", 5),
        ("breast cancer", 4.5), ("lung cancer", 4.5),
        ("skin cancer", 4.5), ("colorectal cancer", 4.5),
        ("cervical cancer", 4.5), ("oral cancer", 4.5),
        ("thyroid disease", 4.5), ("thyroid cancer", 5),
        ("kidney disease", 4.5), ("renal disease", 4.5),
        ("liver disease", 4.5), ("hepatic", 4),
        ("pcos", 4.5), ("polycystic ovary", 5),
        ("leukemia", 5), ("lymphoma", 5), ("melanoma", 5),
        ("retinal disease", 4.5), ("ocular disease", 4.5),
        ("fundus disease", 4.5),
        ("mri classification", 4.5), ("ct classification", 4.5),
        ("healthcare", 3.5), ("medical ai", 4.5), ("ai in healthcare", 5),
        ("ecg classification", 5), ("eeg classification", 5),
        ("eeg-based", 4.5), ("ecg-based", 4.5),
        ("mental health", 4), ("stress detection", 4.5),
        ("autism detection", 4.5), ("fall detection", 4),
        ("wound classification", 4.5), ("wound detection", 4.5),
        ("mortality prediction", 4.5), ("readmission prediction", 4.5),
        ("wearable health", 4), ("health monitoring", 3.5),
        ("smart health", 3.5),
    ],

    "Cybersecurity": [
        ("malware detection", 5), ("malware classification", 5),
        ("malware analysis", 5), ("ransomware", 5),
        ("phishing detection", 5), ("phishing website", 5),
        ("phishing attack", 5), ("sql injection", 5),
        ("zero-day", 5), ("zero day attack", 5),
        ("vulnerability detection", 5), ("vulnerability assessment", 5),
        ("penetration testing", 5), ("exploit", 4.5),
        ("cyber threat", 5), ("cyber attack", 5), ("cyberattack", 5),
        ("cybersecurity", 5), ("cyber security", 5),
        ("steganography", 5), ("steganalysis", 5),
        ("digital forensics", 5), ("digital watermarking", 5),
        ("password authentication", 4.5), ("multi-factor authentication", 5),
        ("data breach", 5), ("privacy-preserving", 4),
        ("side-channel attack", 5), ("adversarial attack", 4.5),
        ("fake news detection", 4.5), ("deepfake detection", 5),
        ("misinformation detection", 4.5),
        ("intrusion detection system", 4.5), ("ids ", 4),
        ("anomaly detection network", 4), ("network anomaly", 4.5),
        ("dos attack", 4.5), ("man-in-the-middle", 5),
        ("data anonymization", 4.5), ("data obfuscation", 4.5),
        ("homomorphic encryption", 5), ("secure multiparty", 5),
        ("differential privacy", 5), ("federated learning privacy", 4.5),
        ("key management", 4), ("public key infrastructure", 5),
        ("digital signature", 4.5), ("hash function", 4),
        ("image forgery", 4.5), ("forgery detection", 4.5),
        ("social engineering", 4.5), ("spam detection", 4),
        ("secure communication", 3.5), ("data security", 3.5),
    ],

    "Cloud Computing": [
        ("cloud computing", 5), ("cloud environment", 5),
        ("cloud service", 4.5), ("cloud platform", 4.5),
        ("cloud infrastructure", 5), ("cloud resource allocation", 5),
        ("cloud resource management", 5), ("cloud workload", 5),
        ("cloud scheduling", 5), ("cloud migration", 5),
        ("cloud security", 4.5), ("cloud storage", 4.5),
        ("virtual machine placement", 5), ("vm scheduling", 5),
        ("vm migration", 5), ("hypervisor", 5),
        ("containerization", 5), ("kubernetes", 5), ("docker ", 4.5),
        ("serverless computing", 5), ("function as a service", 5),
        ("faas", 4.5), ("microservice", 5),
        ("infrastructure as a service", 5), ("iaas", 4.5),
        ("platform as a service", 5), ("paas", 4.5),
        ("software as a service", 5), ("saas", 4.5),
        ("elastic computing", 5), ("auto-scaling", 5),
        ("multi-cloud", 5), ("hybrid cloud", 5), ("federated cloud", 5),
        ("service level agreement", 5), ("sla ", 4.5),
        ("task scheduling cloud", 4.5), ("load balancing cloud", 4.5),
        ("resource provisioning", 4.5), ("cloud cost", 5),
        ("apache spark", 4.5), ("hadoop", 4.5), ("mapreduce", 5),
        ("distributed file system", 4.5), ("hdfs", 5),
        ("securing the cloud", 5), ("cloud threat", 5),
        ("cloud attack", 4.5), ("cloud privacy", 4.5),
        ("cloud vulnerab", 4.5),
    ],

    "Data Science & Big Data": [
        ("big data analytics", 5), ("big data processing", 5),
        ("big data framework", 5), ("data analytics pipeline", 5),
        ("data warehouse", 5), ("data lake", 5),
        ("business intelligence", 5), ("business analytics", 5),
        ("etl process", 5), ("etl pipeline", 5),
        ("data visualization", 4.5), ("dashboard", 4),
        ("frequent pattern mining", 5), ("association rule mining", 5),
        ("frequent itemset", 5), ("apriori algorithm", 5),
        ("knowledge graph", 4.5), ("knowledge discovery", 4.5),
        ("data stream processing", 5), ("stream analytics", 5),
        ("real-time analytics", 4.5),
        ("apache kafka", 5), ("apache flink", 5),
        ("data quality", 4),
        ("recommendation system", 4), ("collaborative filtering", 4.5),
        ("content-based filtering", 5), ("matrix factorization", 4.5),
        ("predictive analytics", 4), ("exploratory data analysis", 4.5),
        ("customer segmentation", 4.5), ("churn prediction", 4.5),
        ("demand forecasting", 4.5), ("supply chain analytics", 4.5),
        ("data mining", 3.5),
    ],

    "Intelligent Systems & Automation": [
        ("autonomous vehicle", 5), ("self-driving", 5),
        ("autonomous driving", 5), ("autonomous robot", 5),
        ("robotic system", 5), ("robotic arm", 5),
        ("industrial robot", 5), ("collaborative robot", 5),
        ("swarm robot", 5), ("uav path", 5), ("drone navigation", 5),
        ("path planning", 4.5), ("motion planning", 4.5),
        ("simultaneous localization and mapping", 5), ("slam ", 4.5),
        ("human-robot interaction", 5), ("human-robot collaboration", 5),
        ("smart manufacturing", 5), ("industry 4.0", 5), ("industry 5.0", 5),
        ("smart factory", 5), ("digital twin", 4.5),
        ("cyber-physical system", 5), ("cyber physical system", 5),
        ("cps ", 4.5), ("scada", 5),
        ("intelligent transportation system", 5),
        ("smart grid", 5), ("smart city", 5), ("smart home", 4.5),
        ("smart meter", 4.5), ("demand response", 4.5),
        ("predictive maintenance", 5), ("condition monitoring", 4.5),
        ("fault diagnosis", 4.5), ("fault detection industrial", 4.5),
        ("process automation", 4.5), ("robotic process automation", 5),
        ("rpa ", 4.5), ("intelligent agent", 4.5),
        ("multi-agent system", 4.5), ("autonomous agent", 4.5),
        ("intelligent control", 4), ("adaptive control", 4),
        ("pid controller", 4), ("fuzzy control", 4),
        ("model predictive control", 4.5),
        ("reinforcement learning control", 4.5),
        ("unmanned aerial", 4.5), ("unmanned vehicle", 5), ("uav ", 4),
        ("embedded system", 3.5), ("automation", 3),
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# BLOCKERS — subtract score when these phrases appear
# ─────────────────────────────────────────────────────────────────────────────
DOMAIN_BLOCKERS = {
    "Networking": [
        ("neural network", -4), ("neural networks", -4),
        ("deep neural", -4), ("convolutional network", -4),
        ("recurrent network", -4), ("bayesian network", -4),
        ("network-based classif", -4), ("network-based detect", -4),
        ("network architecture", -3), ("network model", -3),
        ("social network analys", -4), ("protein network", -4),
        ("gene regulatory network", -4), ("metabolic network", -4),
        ("quorum sensing", -5),
    ],
    "Visual Computing": [
        ("text detection", -2),
    ],
    "Geospatial Computing": [
        ("spatial computing temporal", -2), ("feature spatial", -2),
    ],
    "Advanced Multilingual Computing": [
        ("visual question", -3), ("image captioning", -3), ("visual grounding", -3),
    ],
    "AI in Healthcare": [
        ("plant disease", -20), ("crop disease", -20), ("leaf disease", -20),
        ("paddy disease", -20), ("tomato disease", -20), ("crop prediction", -15),
        ("fertilizer", -15), ("paddy crop", -15), (" plant", -5),
        ("precision agriculture", -15), ("smart agriculture", -15),
        ("crop monitoring", -15), ("crop classification", -15),
        ("plant leaf", -15), ("plant species", -15), ("plant detection", -15),
        ("colocasia", -20), ("cassava", -20), ("maize disease", -20),
        ("rice disease", -20), ("wheat disease", -20), ("mango disease", -20),
        ("citrus plant", -20), ("apple leaf", -20), ("apple disease", -20),
        ("plant pathology", -20), ("plant species", -20), ("plant classif", -20),
        ("disease in plant", -20), ("disease of plant", -20),
        ("in citrus", -20), ("in apple", -15), ("in mango", -15),
        ("quorum sensing", -20), ("antimicrobial", -5), ("peptid", -5),
        ("aquaculture", -10), ("fishery", -10), ("soil moisture", -10),
        ("traffic detection", -10), ("vehicle detection", -10),
        ("lane detection", -10), ("fire detection", -10),
        ("object detection", -5), ("text detection", -5),
        ("fraud detection", -10),
    ],
    "Cybersecurity": [
        ("cloud security architecture", -2), ("network security protocol", -2),
    ],
    "Intelligent Systems & Automation": [
        ("smart pointer", -3), ("smart contract", -3), ("smartphone", -2),
    ],
    "Cloud Computing": [
        ("cloud cover", -4), ("cloud type", -3),
        ("nimbus cloud", -4), ("cumulus", -4),
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# JOURNAL BOOSTS
# ─────────────────────────────────────────────────────────────────────────────
JOURNAL_BOOSTS = {
    "Networking": [
        ("wireless", 3), ("communication", 2.5), ("network", 2),
        ("antenna", 3), ("spectrum", 3), ("mimo", 3), ("ofdm", 3),
        ("sensor network", 3), ("mobile computing", 3),
        ("iot", 2.5), ("vehicular", 3),
    ],
    "Visual Computing": [
        ("image processing", 3), ("computer vision", 3),
        ("visual computing", 3), ("pattern recognition", 2.5), ("graphics", 2.5),
    ],
    "Advanced Multilingual Computing": [
        ("natural language", 3), ("speech", 2.5), ("language processing", 3),
        ("computational linguistics", 3),
    ],
    "Fintech": [
        ("financial", 3), ("finance", 3), ("blockchain", 3),
        ("banking", 3), ("cryptocurrency", 3),
    ],
    "Geospatial Computing": [
        ("geospatial", 3), ("remote sensing", 3), ("gis", 3),
        ("earth observation", 3), ("photogrammetry", 3),
    ],
    "Quantum Computing": [
        ("quantum", 3), ("quantum information", 3),
    ],
    "Accelerated Computing": [
        ("parallel computing", 3), ("high performance", 2.5), ("supercomputing", 3),
    ],
    "Theoretical Computing": [
        ("theoretical computer", 3), ("algorithms", 2.5),
        ("formal methods", 3), ("logic", 2.5), ("computational theory", 3),
    ],
    "Green Computing": [
        ("green computing", 3), ("sustainable computing", 3), ("energy-efficient", 3),
    ],
    "AI in Healthcare": [
        ("biomedical", 3), ("medical", 2.5), ("health", 2.5),
        ("clinical", 3), ("bioinformatics", 3), ("healthcare", 3),
    ],
    "Cybersecurity": [
        ("security", 2.5), ("cryptograph", 3), ("forensic", 3),
        ("cyber", 3), ("privacy", 2.5),
    ],
    "Cloud Computing": [
        ("cloud computing", 3), ("distributed", 2.5), ("grid computing", 3),
        ("cluster computing", 2.5),
    ],
    "Data Science & Big Data": [
        ("data analytics", 3), ("data mining", 3), ("big data", 3),
        ("knowledge", 2.5), ("information system", 2.5),
    ],
    "Intelligent Systems & Automation": [
        ("intelligent system", 3), ("automation", 2.5), ("robotics", 3),
        ("smart system", 3), ("autonomous", 2.5),
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# HEALTHCARE COMBO-MATCHING LISTS
# ─────────────────────────────────────────────────────────────────────────────
MEDICAL_CONDITIONS = [
    "cancer", "tumor", "tumour", "alzheimer", "parkinson", "diabetes",
    "diabetic", "retinopathy", "arrhythmia", "covid", "pneumonia",
    "tuberculosis", "epilep", "seizure", "glaucoma", "cataract",
    "melanoma", "leukemia", "lymphoma", "fracture", "osteoarthritis",
    "dementia", "stroke", "anemia", "anaemia", "sepsis", "obesity",
    "hypertension", "gallstone", "kidney stone", "lung nodule", "polyp",
    "aneurysm", "hemorrhage", "haemorrhage", "ulcer", "psoriasis",
    "autism", "schizophrenia", "mesothelioma", "atrial fibrill",
    "coronary artery", "mitral valve", "aortic",
    "breast tumor", "breast tumour", "brain tumor", "brain tumour",
    "skin lesion", "retinal vessel", "optic disc", "optic cup",
    "blood vessel detection", "chest x-ray", "chest ct",
    "lung nodule", "liver tumor", "kidney tumor", "bone fracture",
    "spinal cord", "thyroid nodule", "cardiac", "myocardial",
    "osteoarthritis", "knee implant", "knee prosthes", "bone marrow",
    "blood cell", "white blood cell", "red blood cell", "platelet",
    "sickle cell", "thalassemia", "psoriasis", "eczema", "dermatitis",
    "macular degeneration", "diabetic macular", "age-related macular",
    "intracranial", "subarachnoid", "subdural", "glioma", "glioblastoma",
    "astrocytoma", "meningioma", "medulloblastoma",
    "covid-19", "sars-cov", "influenza", "dengue", "malaria",
    "hepatitis", "cirrhosis", "fatty liver",
    "chronic kidney", "renal failure", "nephropathy",
    "heart failure", "myocardial infarct", "coronary disease",
    "sleep apnea", "insomnia", "narcolepsy",
    "aortic stenosis", "tricuspid", "ventricular",
    "fundus image", "retinal fundus", "optic nerve",
    "scoliosis", "vertebr", "intervertebral disc",
]

MEDICAL_TASKS = [
    "detection", "diagnosis", "classification", "segmentation",
    "prediction", "recognition", "identification", "analysis",
    "screening", "grading", "staging", "prognosis", "monitoring",
    "detecting", "detecting ", "diagnosing", "classifying",
    "segmenting", "predicting", "discovering",
    "early detection", "early diagnosis", "early prediction",
]

MEDICAL_CONDITION_SCORE = 9.0


# ─────────────────────────────────────────────────────────────────────────────
# SCORING ENGINE
# ─────────────────────────────────────────────────────────────────────────────
def _normalize(text: str) -> str:
    return " " + re.sub(r"\s+", " ", (text or "").strip().lower()) + " "


def _score_text(text: str, keywords: list) -> float:
    return sum(w for phrase, w in keywords if phrase in text)


def classify_paper(title: str, publication_name: str = "", abstract: str = "",
                   min_score: float = 5.0) -> tuple:
    """
    Returns (domain_or_None, score).
    """
    title_norm    = _normalize(title)
    abstract_norm = _normalize(abstract) if abstract else ""
    pub_norm      = _normalize(publication_name)

    scores = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        t_score = _score_text(title_norm, keywords) * 3
        a_score = _score_text(abstract_norm, keywords) if abstract else 0
        scores[domain] = t_score + a_score

    combined_norm = title_norm + " " + abstract_norm
    for domain, blockers in DOMAIN_BLOCKERS.items():
        scores[domain] = scores.get(domain, 0) + _score_text(combined_norm, blockers)

    for domain, boosts in JOURNAL_BOOSTS.items():
        if scores.get(domain, 0) > 0:
            scores[domain] += _score_text(pub_norm, boosts)

    scores = {k: max(0.0, v) for k, v in scores.items()}

    # Healthcare combo-matching
    plant_blocker = any(b in title_norm for b in [
        "plant disease", "crop disease", "leaf disease", "paddy disease",
        "tomato disease", "crop prediction", "fertilizer", "plant pathology",
        "plant species", "plant classif", "citrus plant", "apple leaf",
    ])
    has_condition = any(c in title_norm for c in MEDICAL_CONDITIONS)
    has_task      = any(t in title_norm for t in MEDICAL_TASKS)
    if has_condition and has_task and not plant_blocker:
        if scores.get("AI in Healthcare", 0) < MEDICAL_CONDITION_SCORE:
            scores["AI in Healthcare"] = MEDICAL_CONDITION_SCORE

    scores = {k: max(0.0, v) for k, v in scores.items()}
    best_domain = max(scores, key=scores.get)
    best_score  = scores[best_domain]

    if best_score < min_score:
        return (None, 0.0)
    return (best_domain, round(best_score, 1))


# ─────────────────────────────────────────────────────────────────────────────
# DATABASE — exact schema
#   papers : id, scopus_id, title, publication_name, domain  (+ other cols)
#   users  : scopus_id, department
#   Join   : papers.scopus_id = users.scopus_id
#   Filter : users.department = 'C.Tech'
# ─────────────────────────────────────────────────────────────────────────────

# SQL to fetch every C.Tech paper that needs classification
# Pulls all papers whose author (scopus_id) belongs to a C.Tech user.
FETCH_CTECH_PAPERS = """
    SELECT DISTINCT
        p.id,
        p.title,
        p.publication_name
    FROM   papers p
    INNER JOIN users u ON u.scopus_id = p.scopus_id
    WHERE  u.department = 'C.Tech'
"""

# Same query but only papers where domain is currently NULL or empty —
# use this if you want to skip already-classified papers on re-runs.
FETCH_UNCLASSIFIED_ONLY = """
    SELECT DISTINCT
        p.id,
        p.title,
        p.publication_name
    FROM   papers p
    INNER JOIN users u ON u.scopus_id = p.scopus_id
    WHERE  u.department = 'C.Tech'
      AND  (p.domain IS NULL OR p.domain = '')
"""


def get_connection():
    try:
        import mysql.connector
    except ImportError:
        print("ERROR: mysql-connector-python is not installed.")
        print("  Run:  pip install mysql-connector-python")
        sys.exit(1)

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"ERROR: Could not connect to database — {e}")
        print("\nCheck DB_CONFIG at the top of this file.")
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    # Whether to skip papers that already have a domain value
    skip_classified = "--skip-existing" in sys.argv

    mode_label = []
    if DRY_RUN:        mode_label.append("DRY RUN")
    if skip_classified: mode_label.append("SKIP EXISTING")
    mode_str = " | ".join(mode_label) if mode_label else "LIVE"

    print(f"\n{'='*62}")
    print(f"  Paper Domain Classifier — DB Edition  [{mode_str}]")
    print(f"  Database : {DB_CONFIG['database']}  @  {DB_CONFIG['host']}")
    print(f"{'='*62}\n")

    # ── 1. Connect
    print("Connecting to database...")
    conn   = get_connection()
    cursor = conn.cursor()
    print(f"  Connected.\n")

    # ── 2. Fetch C.Tech papers
    query = FETCH_UNCLASSIFIED_ONLY if skip_classified else FETCH_CTECH_PAPERS
    label = "unclassified C.Tech" if skip_classified else "all C.Tech"
    print(f"Fetching {label} papers...")

    cursor.execute(query)
    rows  = cursor.fetchall()
    total = len(rows)
    print(f"  Found {total} papers.\n")

    if total == 0:
        if skip_classified:
            print("All C.Tech papers already have a domain. Nothing to do.")
        else:
            print("No C.Tech papers found.")
            print("Verify that users.department = 'C.Tech' exists in your database.")
        conn.close()
        return

    # ── 3. Classify
    print(f"Classifying {total} papers...")
    results = []          # list of (paper_id, domain_or_empty_string)
    dist    = Counter()

    for i, (paper_id, title, pub_name) in enumerate(rows, 1):
        domain, score = classify_paper(
            title            = title    or "",
            publication_name = pub_name or "",
            min_score        = MIN_SCORE,
        )
        results.append((paper_id, domain or ""))
        dist[domain or ""] += 1

        if i % 500 == 0 or i == total:
            classified_so_far = sum(v for k, v in dist.items() if k)
            print(f"  [{i:>5}/{total}]  classified: {classified_so_far}")

    # ── 4. Write to DB  (or preview)
    if DRY_RUN:
        print("\n[DRY RUN] No changes written. Sample of what would be updated:")
        print(f"  {'ID':<8}  {'Domain'}")
        print(f"  {'─'*8}  {'─'*40}")
        for paper_id, domain in results[:25]:
            print(f"  {paper_id:<8}  {domain or '(unclassified)'}")
        if total > 25:
            print(f"  ... and {total - 25} more rows.")
    else:
        print(f"\nWriting domain values back to database...")
        update_sql = "UPDATE papers SET domain = %s WHERE id = %s"
        # Store empty string as NULL so unclassified rows stay clean
        batch = [(domain if domain else None, pid) for pid, domain in results]
        cursor.executemany(update_sql, batch)
        conn.commit()
        rows_updated = cursor.rowcount
        print(f"  {rows_updated} rows updated.\n")

    # ── 5. Summary
    total_classified   = sum(v for k, v in dist.items() if k)
    total_unclassified = dist.get("", 0)

    print(f"\n{'─'*62}")
    print(f"  SUMMARY")
    print(f"{'─'*62}")
    print(f"  Total C.Tech papers processed : {total}")
    print(f"  Classified                    : {total_classified}  ({total_classified/total*100:.1f}%)")
    print(f"  Unclassified (domain = NULL)  : {total_unclassified}  ({total_unclassified/total*100:.1f}%)")
    print(f"\n  Domain breakdown:")
    for domain, count in sorted(dist.items(), key=lambda x: -x[1]):
        label = domain if domain else "(unclassified)"
        print(f"    {label:<44} {count:>5}  ({count/total*100:.1f}%)")

    conn.close()
    print(f"\n{'='*62}\n")


if __name__ == "__main__":
    main()