import fs from 'fs/promises';
import path from 'path';
import yaml from 'yaml';

/**
 * SkillService - 技能管理服务
 * 支持 .js 逻辑技能 和 标准 .md 知识技能
 */
class SkillService {
  constructor(config = {}) {
    this.directory = path.resolve(process.cwd(), config.directory || './skills');
  }

  async init() {
    try {
      await fs.mkdir(this.directory, { recursive: true });
      console.log(`[Skill] Service initialized, directory: ${this.directory}`);
    } catch (error) {
      console.error('[Skill] Init error:', error.message);
    }
  }

  /**
   * 解析 SKILL.md 的前置参数 (Frontmatter)
   */
  _parseFrontmatter(content) {
    const match = content.match(/^---\r?\n([\s\S]*?)\r?\n---/);
    if (!match) return { content };
    
    try {
      const metadata = yaml.parse(match[1]);
      const body = content.slice(match[0].length).trim();
      return { metadata, content: body };
    } catch (e) {
      return { content };
    }
  }

  /**
   * 列出所有可用技能
   */
  async list() {
    try {
      const entries = await fs.readdir(this.directory, { withFileTypes: true });
      const skills = [];

      for (const entry of entries) {
        if (entry.isFile() && entry.name.endsWith('.js')) {
          skills.push({ name: entry.name.replace('.js', ''), type: 'js' });
        } else if (entry.isDirectory()) {
          const subDirPath = path.join(this.directory, entry.name);
          const subFiles = await fs.readdir(subDirPath);
          
          if (subFiles.includes('SKILL.md')) {
            const content = await fs.readFile(path.join(subDirPath, 'SKILL.md'), 'utf8');
            const { metadata } = this._parseFrontmatter(content);
            skills.push({
              name: metadata?.name || entry.name,
              description: metadata?.description || '',
              type: 'md'
            });
          } else if (subFiles.includes('index.js')) {
            skills.push({ name: entry.name, type: 'js' });
          }
        }
      }
      return skills;
    } catch (error) {
      console.error('[Skill] List skills error:', error.message);
      return [];
    }
  }

  /**
   * 执行指定技能
   */
  async run(name, params = {}, agent) {
    const possiblePaths = [
      path.join(this.directory, `${name}.js`),
      path.join(this.directory, name, 'index.js'),
      path.join(this.directory, name, 'SKILL.md'),
    ];

    let foundPath = null;
    for (const p of possiblePaths) {
      try {
        const stats = await fs.stat(p);
        if (stats.isFile()) {
          foundPath = p;
          break;
        }
      } catch (e) {
        // 文件不存在，继续尝试下一个路径
      }
    }

    if (!foundPath) throw new Error(`Skill "${name}" not found`);

    try {
      if (foundPath.endsWith('.js')) {
        const module = await import(`file://${foundPath}?t=${Date.now()}`);
        const executeFn = module.default || module.execute;
        return await executeFn(agent, params);
      } else if (foundPath.endsWith('.md')) {
        const rawContent = await fs.readFile(foundPath, 'utf8');
        const { metadata, content } = this._parseFrontmatter(rawContent);
        
        console.log(`[Skill] Executing Standard Markdown skill: ${name}`);
        
        const prompt = `你现在正在使用 "${name}" 技能。
技能描述: ${metadata?.description || '无'}
参考手册/示例:
${content}

请根据以上信息，结合用户参数 ${JSON.stringify(params)} 并在必要时调用 cmd_exec 或其它工具来完成任务。`;

        return await agent.decide(prompt, {
          appendSystemPrompt: `你已临时获得 "${name}" 技能的专业知识，请严格按照其提供的最佳实践行动。`,
        });
      }
    } catch (error) {
      console.error(`[Skill] Error running skill "${name}":`, error.message);
      throw error;
    }
  }
}

export default SkillService;
