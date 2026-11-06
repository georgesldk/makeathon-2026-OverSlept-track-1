# Data sources

Licences checked on 3-4 November 2026.
Raw downloads and API caches are not committed to git.


## Sources we use

### Culpeper, The Complete Herbal
- Folder:   historical_texts/culpeper/
- Licence:  no copyright restriction (Project Gutenberg #49513)
- We must:  only use the name "Project Gutenberg" to cite it

### Dioscorides, De materia medica (Wellmann's Greek edition)
- Folder:   historical_texts/dioscorides/
- Licence:  CC BY-SA 4.0 (First1KGreek TEI of Wellmann 1906-1914)
- We must:  credit Wellmann, First1KGreek and Harvard College
            Library; share anything built from the text under
            CC BY-SA 4.0 too
- Read it:  https://scaife.perseus.org/reader/urn:cts:greekLit:tlg0656.tlg001.1st1K-grc1:1.preface.1-1.preface.5/

### Shennong Bencao Jing (Sun Xingyan's edition, Chinese Wikisource)
- Folder:   historical_texts/shennong/
- What:     the Han materia medica (1st-2nd c. AD), lost and reconstructed;
            Sun Xingyan and Sun Fengyi's edition (1799), Wikisource revision
            11135696. The plain one-page version (no edition named) is used
            only to cross-check entries and their kind
- Licence:  text public domain; Wikisource transcription CC BY-SA 4.0
- We must:  credit Sun Xingyan and Chinese Wikisource; share what is built
            from the transcription under CC BY-SA 4.0
- Read it:  https://zh.wikisource.org/wiki/神農本草經_(孫星衍)

### Bretschneider, Botanicon Sinicum, Part III (1895)
- Folder:   reference_sources/bretschneider/ (BHL OCR), historical_texts/shennong/
- What:     "Botanical investigations into the materia medica of the ancient
            Chinese": the Shennong drugs one by one, with identifications
- Licence:  public domain; through the Biodiversity Heritage Library (item 23159)
- Note:     the OCR lost the Chinese characters; entries are matched by
            romanisation, and identifications read with checked quotes

### Wikidata, Chinese labels (Shennong)
- Folder:   common_name_sources/wikidata/shennong/
- What:     taxa with a Chinese label or alias equal to a drug's name, and
            crude-drug items naming their source taxon (P1582); SPARQL
- Licence:  CC0

### LSJ Greek-English Lexicon (Perseus)
- Folder:   reference_sources/lsj/
- Licence:  CC BY-SA (Perseus Digital Library)
- We must:  credit Perseus with a link to http://www.perseus.tufts.edu/
            and to https://github.com/PerseusDL/lexica; offer any
            corrections to Perseus; share what we build from it
            under CC BY-SA
- Note:     its plant identifications (1940) are scholars' opinions;
            we keep them as a separate, labelled layer

### GBIF
- Folder:   common_name_sources/gbif/
- Licence:  CC BY 4.0 (some common names are CC BY-NC)
- We must:  credit GBIF

### Wikidata
- Folder:   common_name_sources/wikidata/
- Licence:  CC0
- We must:  nothing

### iNaturalist
- Folder:   common_name_sources/inaturalist/
- Licence:  not stated
- We must:  see the notes below

### ChecklistBank (Catalogue of Life, ITIS, and others)
- Folder:   common_name_sources/checklistbank/
- Licence:  set per checklist (Catalogue of Life is CC BY 4.0)
- We must:  credit each checklist we use (its licence is stored per hit)

### NCBI Taxonomy (through TaxTree)
- Folder:   common_name_sources/taxtree/
- Licence:  public domain
- We must:  acknowledge NCBI

### Dr. Duke's Databases (USDA)
- Folder:   common_name_sources/drduke/
- Licence:  CC0
- We must:  nothing

### WCVP (Kew)
- Folder:   scientific_name_sources/wcvp/
- Licence:  CC BY 3.0
- We must:  credit Kew and give the version

### World Flora Online (WFO Plant List)
- Folder:   scientific_name_sources/wfo/
- Licence:  CC0
- We must:  nothing; we cite it and give the release (2026-06)

### IPNI (through the hackathon-hosted API)
- Folder:   scientific_name_sources/ipni/
- Licence:  CC BY 3.0 (IPNI data)
- We must:  credit IPNI; the hackathon API is not an official
            IPNI service

### Global Names Verifier
- Folder:   scientific_name_sources/globalnames/
- Licence:  free service; each record keeps its own database's
            licence
- We must:  credit Global Names and the database behind each
            record we use


### Biodiversity Heritage Library (BHL)
- Folder:   description_sources/bhl/
- Licence:  most scanned books are public domain; BHL's own data
            CC0; each book keeps its own rights statement
- We must:  credit BHL and the book (title, year, page link are
            kept with every passage)

### Wikipedia (English)
- Folder:   description_sources/wikipedia/
- Licence:  CC BY-SA 4.0
- We must:  credit Wikipedia and link the article; anything we
            publish that contains its text is CC BY-SA too
- Used as weak evidence only (ELIGIBILITY_RULES.md, D7)

### MeSH, Medical Subject Headings (NLM)
- Folder:   reference_sources/mesh/ (desc2026.gz not in git; mesh_index.json.gz in git)
- Licence:  public domain (U.S. government work), NLM terms and conditions
- We must:  credit "Courtesy of the U.S. National Library of Medicine" and give the MeSH year
- Used as the shared concept vocabulary for medicinal claims (claims/CLAIMS_METHOD.md)

### Disease Ontology (DOID)
- Folder:   reference_sources/doid/ (doid.obo not in git)
- Licence:  CC0
- We must:  nothing; we cite it and give the release (2026-10-29)
- Used to map old medical terms to MeSH (claims/map_historical_terms.py)

### NCBI E-utilities / PubMed
- Folder:   claims/check_mesh_ncbi.py
- Licence:  free service; NCBI usage guidelines (at most 3 requests a second without a key)
- We must:  follow the usage guidelines; credit NCBI

### Europe PMC (EMBL-EBI)
- Folder:   stage3/retrieve.py (cache in stage3/cache/epmc/, not in git)
- Licence:  free REST API; article text keeps its own licence (we use open-access full text only)
- We must:  credit Europe PMC; keep stored texts outside git

### ClinicalTrials.gov (API v2, NLM)
- Folder:   stage3/retrieve.py (cache in stage3/cache/ctgov/, not in git)
- Licence:  public domain (US government); NLM terms of use
- We must:  credit ClinicalTrials.gov and give the retrieval date

### EMA herbal monographs (HMPC)
- Folder:   stage3/retrieve.py (table and PDFs cached in stage3/cache/ema/, not in git)
- Licence:  EMA content may be reproduced with the source acknowledged
- We must:  acknowledge EMA as the source; say which monograph and version

### Lardos et al. 2024, research data (figshare)
- Folder:   description_sources/paper_test/data/ (not in git)
- Licence:  not stated on the share link; the paper is CC BY 4.0
- We must:  cite the paper; we do not redistribute the data files
- Used to test the AI description check against the experts' scores, and (data file 7) Stage 3
  retrieval and extraction against the experts' clinical studies


## Notes

- Some GBIF and ChecklistBank common names are non-commercial (CC BY-NC).
  Anything we publish from them is non-commercial too, unless those
  records are removed.
- iNaturalist asks that its API not be used to collect data in bulk.
  We use the API for now, within its rate limit; its Taxonomy
  download is the alternative if needed.


## Sources we do not use

- Osbaldeston's English Dioscorides (Ibidis Press, 2000): copyrighted.
  Replaced by Wellmann's Greek edition above.
- POWO: blocks scripts. WCVP has the same data.
- Kew MPNS: licensed access only.
- Plants For A Future: copyrighted.
- Native American Ethnobotany Database: community rights.
- Chinese Text Project (ctext.org), the dataset list's Chinese source: its API
  gives this book only to institutional subscribers, and its site forbids
  scraping (and says it corrupts what scrapers get). Chinese Wikisource is used.


## Citations

- Culpeper, N. The Complete Herbal. Project Gutenberg #49513.
  https://www.gutenberg.org/ebooks/49513
- Dioscorides. De materia medica, ed. M. Wellmann, 3 vols, Berlin
  1906-1914. TEI: First1KGreek, Harvard College Library / University
  of Leipzig, 2018. urn:cts:greekLit:tlg0656.tlg001.1st1K-grc1
- Liddell, H. G., Scott, R., Jones, H. S. A Greek-English Lexicon,
  9th ed. (Oxford 1940). Machine-readable edition: Perseus Digital
  Library, Tufts University. https://github.com/PerseusDL/lexica
- GBIF Secretariat. GBIF Backbone Taxonomy. doi:10.15468/39omei
- Wikidata. https://www.wikidata.org
- iNaturalist. https://www.inaturalist.org
- ChecklistBank: the citation shown for each checklist, for example
  https://www.checklistbank.org/dataset/313100/about
- Schoch, C. L. et al. (2020). NCBI Taxonomy. Database 2020: baaa062.
- USDA ARS. Dr. Duke's Phytochemical and Ethnobotanical Databases.
  doi:10.15482/USDA.ADC/1239279
- Govaerts, R. (ed.) (2026). WCVP, version 16. Royal Botanic Gardens,
  Kew. doi:10.34885/egs6-cp24
- WFO (2026). World Flora Online Plant List, release 2026-06.
  https://list.worldfloraonline.org
- IPNI (2026). International Plant Names Index. The Royal Botanic
  Gardens, Kew, Harvard University Herbaria & Libraries and
  Australian National Herbarium. https://www.ipni.org
- Global Names Verifier. https://verifier.globalnames.org
- Biodiversity Heritage Library. https://www.biodiversitylibrary.org
- U.S. National Library of Medicine. Medical Subject Headings (MeSH), 2026. https://www.nlm.nih.gov/mesh/
- NCBI. Entrez Programming Utilities. https://www.ncbi.nlm.nih.gov/books/NBK25499/
- Schriml, L. M. et al. Human Disease Ontology. https://disease-ontology.org (release 2026-10-29)
- Wikipedia, The Free Encyclopedia. https://en.wikipedia.org
- Europe PMC Consortium. Europe PMC. https://europepmc.org
- U.S. National Library of Medicine. ClinicalTrials.gov, API v2. https://clinicaltrials.gov/data-api/api
- European Medicines Agency, Committee on Herbal Medicinal Products. EU herbal monographs.
  https://www.ema.europa.eu/en/medicines/download-medicine-data (herbal medicines table)
- Lardos, A., Patmore, K., Allkin, R., Lazarou, R., Nesbitt, M.,
  Scott, A. C., Zipser, B. (2024). A systematic methodology to assess
  the identity of plants in historical texts. Journal of
  Ethnopharmacology 322, 117622. doi:10.1016/j.jep.2023.117622.
  Data: https://figshare.com/s/2e0f64b5794892ed4679
