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
    "This page is set up for four team members. Replace the placeholder roles, bios, and images below as your final copy is ready.",
  members: [
    {
      id: "sk-pi",
      name: "SK-PI",
      role: "Role / title placeholder",
      imageSrc: "/about/team/sk-pi.jpg",
      imageAlt: "Portrait placeholder for SK-PI",
      bio:
        "Add a short bio here covering background, expertise, and role on docent.ID.",
    },
    {
      id: "az",
      name: "AZ",
      role: "Role / title placeholder",
      imageSrc: "/about/team/az.jpg",
      imageAlt: "Portrait placeholder for AZ",
      bio:
        "Add a short bio here covering background, expertise, and role on docent.ID.",
    },
    {
      id: "rc",
      name: "RC",
      role: "Role / title placeholder",
      imageSrc: "/about/team/rc.jpg",
      imageAlt: "Portrait placeholder for RC",
      bio:
        "Add a short bio here covering background, expertise, and role on docent.ID.",
    },
    {
      id: "sk",
      name: "SK",
      role: "Role / title placeholder",
      imageSrc: "/about/team/sk.jpg",
      imageAlt: "Portrait placeholder for SK",
      bio:
        "Add a short bio here covering background, expertise, and role on docent.ID.",
    },
  ],
};
