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
