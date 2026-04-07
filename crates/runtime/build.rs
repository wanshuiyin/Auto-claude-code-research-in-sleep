use std::env;
use std::fs;
use std::path::Path;

fn main() {
    let out_dir = env::var("OUT_DIR").unwrap();
    let out_path = Path::new(&out_dir);
    let assets_dir = Path::new("assets/skills");

    println!("cargo:rerun-if-changed=assets/skills");

    let mut skill_names: Vec<String> = Vec::new();
    let mut resource_entries: Vec<(String, String)> = Vec::new(); // (key, filename)

    if assets_dir.exists() {
        let mut dirs: Vec<_> = fs::read_dir(assets_dir)
            .expect("read assets/skills")
            .filter_map(Result::ok)
            .filter(|e| e.file_type().map_or(false, |t| t.is_dir()))
            .collect();
        dirs.sort_by_key(|e| e.file_name());

        let skills_out = out_path.join("skills");
        fs::create_dir_all(&skills_out).expect("create skills out dir");

        for entry in dirs {
            let skill_md = entry.path().join("SKILL.md");
            if skill_md.exists() {
                let name = entry.file_name().to_string_lossy().to_string();
                // Copy skill file to OUT_DIR so include_str! can reference it
                let dest = skills_out.join(format!("{name}.md"));
                fs::copy(&skill_md, &dest).expect("copy skill file");
                skill_names.push(name.clone());

                // Also embed helper files (.py, .sh) in the same directory
                if let Ok(files) = fs::read_dir(entry.path()) {
                    for file in files.filter_map(Result::ok) {
                        let fname = file.file_name().to_string_lossy().to_string();
                        let is_helper = fname.ends_with(".py") || fname.ends_with(".sh");
                        if is_helper && file.file_type().map_or(false, |t| t.is_file()) {
                            let out_name = format!("{name}__{fname}");
                            let dest = skills_out.join(&out_name);
                            fs::copy(file.path(), &dest).expect("copy helper file");
                            let key = format!("{name}/{fname}");
                            resource_entries.push((key, out_name));
                        }
                    }
                }
            }
        }
    }

    // Generate Rust source for bundled skills
    let mut code = String::from(
        "/// Bundled ARIS skills compiled into the binary.\n\
         pub static BUNDLED_SKILLS: &[(&str, &str)] = &[\n",
    );
    for name in &skill_names {
        code.push_str(&format!(
            "    (\"{name}\", include_str!(concat!(env!(\"OUT_DIR\"), \"/skills/{name}.md\"))),\n"
        ));
    }
    code.push_str("];\n\n");

    // Generate Rust source for bundled helper resources
    code.push_str(
        "/// Bundled helper files (Python/Shell scripts) for skills.\n\
         pub static BUNDLED_RESOURCES: &[(&str, &str)] = &[\n",
    );
    for (key, out_name) in &resource_entries {
        code.push_str(&format!(
            "    (\"{key}\", include_str!(concat!(env!(\"OUT_DIR\"), \"/skills/{out_name}\"))),\n"
        ));
    }
    code.push_str("];\n");

    fs::write(out_path.join("bundled_skills.rs"), code).expect("write bundled_skills.rs");

    println!(
        "cargo:warning=Embedded {} bundled skills, {} helper resources",
        skill_names.len(),
        resource_entries.len()
    );
}
