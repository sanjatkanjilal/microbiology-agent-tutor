export const ABOUT_ARCHITECTURE_CONTENT = {
  title: "About docent.ID",
  intro: [
    "docent.ID is an infectious diseases teaching product built around real MGH ID Images cases, a Socratic tutoring experience, and a modular clinical reasoning workflow for trainees.",
    "Instead of giving learners a static answer sheet, the product places them inside a case. They gather history, work through the differential, justify management decisions, and learn the pathophysiology through guided questioning.",
  ],
  productHighlights: [
    {
      title: "Real case corpus",
      body: "The platform uses the imported ID Images case library so students can work through authentic infectious diseases cases and review images, writeups, and diagnoses in one place.",
    },
    {
      title: "Socratic tutor",
      body: "A multi-agent tutoring flow is designed to teach by prompting, questioning, and clarifying rather than simply revealing the diagnosis too early.",
    },
    {
      title: "Modular learning",
      body: "Students can focus on history taking, differential diagnosis, management, or pathophysiology and epidemiology depending on what they need to practice.",
    },
    {
      title: "Human-reviewed metadata",
      body: "Cases can be tagged by pathogen, syndrome, and host features, with a dedicated review workflow so faculty or domain experts can validate the automatically generated suggestions.",
    },
  ],
  architectureHighlights: [
    {
      title: "Case source layer",
      body: "MGH ID Images cases and associated figures are parsed into the local case library and made available to the frontend and tutoring workflow.",
    },
    {
      title: "Tutor orchestration layer",
      body: "The backend coordinates tutoring behavior, case setup, chat flows, and module-aware transitions so the learner stays in the right educational context.",
    },
    {
      title: "Knowledge and feedback layer",
      body: "Guideline retrieval, case review, and future expert-tag validation support both instruction quality and data quality over time.",
    },
  ],
  imageSlots: [
    {
      title: "Product screenshot",
      src: "/about/architecture/product-overview.png",
      alt: "docent.ID product screenshot placeholder",
      caption: "Drop a screenshot of the main learner experience here.",
    },
    {
      title: "Architecture diagram",
      src: "/about/architecture/agent-architecture.png",
      alt: "docent.ID architecture diagram placeholder",
      caption: "Drop a system diagram here showing the case corpus, tutoring agents, retrieval layer, and review tooling.",
    },
  ],
};

export const ABOUT_TEAM_CONTENT = {
  intro:
    "Meet the docent.ID team and open each profile for a fuller background and bio.",
  members: [
    {
      id: "sk-pi",
      name: "Dr. Sanjat Kanjilal",
      role: "Principal Investigator",
      imageSrc: "/about/team/sk-pi.jpg",
      imageAlt: "Portrait of Dr. Sanjat Kanjilal",
      bio: [
        "Sanjat Kanjilal is a physician-scientist, an infectious diseases physician, and a clinical microbiologist. He is the former director of the microbiology and infectious diseases course (HST 040) and an integrative physiology course (I2MS 2) for pre-clinical medical students in the Harvard-MIT Health Sciences and Technology (HST) program at Harvard Medical School and the Massachusetts Institute of Technology. He was a key member of a multi-year curriculum reform to fundamentally re-orient HST's strategy for preparing physician-scientists for research and practice in the 21st century. In addition to teaching medical students, Dr. Kanjilal attended on the Bigelow General Medicine teaching service at Massachusetts General Hospital and contributed to the training of both infectious diseases and clinical microbiology fellows at Brigham and Women's Hospital. He also has experience in the classroom from low-resource settings, having taught basic physiology to medical students in Southern Sudan at the Juba University School of Medicine.",
        "Dr. Kanjilal has a history of innovation in medical education, having revamped HST 040 and built I2MS 2 from the ground up based on the following principles: opportunities to teach real-time clinical decision making in the face of uncertainty; a highly interactive classroom where the focus is on participation via the Socratic method; an explicit emphasis on approaching clinical problems from basic principles of pathophysiology rather than pattern recognition; coherent narratives to explicitly connect micro-scale events to macro phenomena via all scales in between; inclusion of cutting-edge, rigorous basic and translational research tailored to in-class topics; slide formats incorporating design principles for effective learning; and integration of AI and other educational technologies to support active learning of basic principles.",
        "Dr. Kanjilal is currently a faculty member at Amsterdam University Medical Center where he heads the Microbiology Informatics Team. His research focus is on building robust, comprehensive, and safe learning health systems from multimodal observational health data.",
      ],
    },
    {
      id: "az",
      name: "Andrew Zhou",
      role: "Research Assistant",
      imageSrc: "/about/team/az.jpg",
      imageAlt: "Portrait of Andrew Zhou",
      bio: [
        "Andrew is a medical student in the Harvard-MIT Health Sciences and Technology program. He graduated from Caltech with a degree in Chemistry in 2021 and from the University of Cambridge with an MPhil in 2022.",
        "He hopes to become an oncologist, and his research interests are in protein engineering, computational biology, and genetics. Outside of academics, he enjoys playing tennis, running, hiking, skiing, and playing the cello.",
      ],
    },
    {
      id: "rc",
      name: "Riccardo Conci",
      role: "Research Assistant",
      imageSrc: "/about/team/rc.jpeg",
      imageAlt: "Portrait of Riccardo Conci",
      bio: [
        "Riccardo is a Ph.D. student in the Artificial Intelligence in Medicine program at Harvard. He graduated from the University of Cambridge with degrees in Computer Science, Computational Biology, and Neuroscience.",
        "He also served as an acute medicine doctor in the NHS, training at Addenbrooke's and Milton Keynes University Hospital.",
        "His research interests are in machine learning, natural language processing, and computational biology. Outside of academics, he enjoys singing and playing the piano.",
      ],
    },
    {
      id: "sk",
      name: "Sukanya Krishna",
      role: "Research Assistant",
      imageSrc: "/about/team/sk.jpg",
      imageAlt: "Portrait of Sukanya Krishna",
      bio: [
        "Sukanya is a Ph.D. student in the Computer Science program at Harvard. Her research interests sit broadly in trustworthy machine learning and evaluation of large language models. She is particularly interested in the intersection of machine learning and healthcare, and her work focuses on developing methods to improve the reliability and interpretability of AI systems in clinical settings.",
        "Outside of academics, she enjoys running and hiking, reading manga, and baking.",
      ],
    },
  ],
};
